"""Workflow orchestration engine — sequential DAG + HITL pause/resume."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import Agent
from app.models.approval import ApprovalRequest
from app.models.workflow import WorkflowDefinition, WorkflowRun, WorkflowStep
from app.services.audit import record_audit
from app.workflows.catalog import BUILTIN_WORKFLOWS


async def ensure_builtin_workflows(db: AsyncSession, tenant_id: UUID) -> int:
    created = 0
    for spec in BUILTIN_WORKFLOWS:
        existing = await db.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.tenant_id == tenant_id,
                WorkflowDefinition.slug == spec["slug"],
                WorkflowDefinition.version == spec["version"],
            )
        )
        if existing:
            continue
        db.add(
            WorkflowDefinition(
                tenant_id=tenant_id,
                slug=spec["slug"],
                name=spec["name"],
                description=spec.get("description"),
                domain=spec.get("domain") or "AD",
                version=spec["version"],
                graph=spec.get("graph") or {},
                sample_input=spec.get("sample_input") or {},
                tags=spec.get("tags") or [],
                is_active=True,
                is_builtin=True,
            )
        )
        created += 1
    if created:
        await db.flush()
    return created


def _nodes_by_id(graph: dict) -> dict[str, dict]:
    return {n["id"]: n for n in (graph.get("nodes") or []) if isinstance(n, dict) and n.get("id")}


def _start_nodes(graph: dict) -> list[str]:
    nodes = _nodes_by_id(graph)
    targets = {e.get("to") for e in (graph.get("edges") or []) if isinstance(e, dict)}
    starts = [nid for nid in nodes if nid not in targets]
    return starts or list(nodes.keys())[:1]


def _next_nodes(graph: dict, node_id: str) -> list[str]:
    return [
        e["to"]
        for e in (graph.get("edges") or [])
        if isinstance(e, dict) and e.get("from") == node_id and e.get("to")
    ]


def _build_agent_input(node: dict, context: dict, run_input: dict) -> dict:
    cfg = node.get("config") or {}
    if cfg.get("input_from") == "input":
        return dict(run_input)
    input_map = cfg.get("input_map") or {}
    if input_map:
        out: dict[str, Any] = {}
        for out_key, src in input_map.items():
            if src in context:
                out[out_key] = context[src]
            elif src in run_input:
                out[out_key] = run_input[src]
            elif src in context.get("input", {}):
                out[out_key] = context["input"][src]
        # Always keep original input available
        out.setdefault("context_snapshot", {k: context.get(k) for k in list(context)[:12]})
        return out or dict(run_input)
    return dict(run_input)


async def _resolve_agent(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    node: dict,
    bindings: dict[str, str],
) -> Agent | None:
    node_id = node["id"]
    if node_id in bindings and bindings[node_id]:
        try:
            aid = UUID(str(bindings[node_id]))
        except ValueError:
            aid = None
        if aid:
            agent = await db.get(Agent, aid)
            if agent and agent.tenant_id == tenant_id:
                return agent

    domain = (node.get("config") or {}).get("domain")
    q = select(Agent).where(Agent.tenant_id == tenant_id)
    if domain:
        q = q.where(func.upper(Agent.domain) == str(domain).upper())
    q = q.order_by(Agent.created_at.desc()).limit(1)
    return await db.scalar(q)


async def _load_run(db: AsyncSession, run_id: UUID, tenant_id: UUID) -> WorkflowRun:
    # Expire any cached instance so selectinload picks up newly flushed steps
    cached = await db.get(WorkflowRun, run_id)
    if cached is not None:
        await db.refresh(cached, attribute_names=["steps", "definition", "context", "status"])

    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.tenant_id == tenant_id)
        .options(
            selectinload(WorkflowRun.steps),
            selectinload(WorkflowRun.definition),
        )
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise LookupError("Workflow run not found")
    return run


async def start_run(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    definition: WorkflowDefinition,
    input_payload: dict,
    agent_bindings: dict[str, str] | None = None,
    name: str | None = None,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> WorkflowRun:
    graph = definition.graph or {}
    starts = _start_nodes(graph)
    if not starts:
        raise ValueError("Workflow graph has no nodes")

    run = WorkflowRun(
        tenant_id=tenant_id,
        definition_id=definition.id,
        name=name or f"{definition.name} run",
        status="running",
        input_payload=input_payload or {},
        context={"input": input_payload or {}},
        agent_bindings=agent_bindings or {},
        current_node_id=starts[0],
        started_by=actor_id,
    )
    db.add(run)
    await db.flush()

    await record_audit(
        db,
        tenant_id=tenant_id,
        action="workflow.started",
        resource_type="workflow_run",
        resource_id=str(run.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"definition": definition.slug, "start": starts[0]},
    )

    await advance_run(
        db,
        run_id=run.id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_email=actor_email,
    )
    return await _load_run(db, run.id, tenant_id)


async def advance_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    tenant_id: UUID,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> WorkflowRun:
    """Execute nodes until HITL pause, terminal success, or failure."""
    run = await _load_run(db, run_id, tenant_id)
    if run.status in {"succeeded", "failed", "cancelled"}:
        return run
    if run.status == "awaiting_approval":
        return run

    definition = run.definition
    if definition is None:
        definition = await db.get(WorkflowDefinition, run.definition_id)
    if definition is None:
        raise LookupError("Workflow definition not found")

    graph = definition.graph or {}
    nodes = _nodes_by_id(graph)
    context = dict(run.context or {})
    bindings = {str(k): str(v) for k, v in (run.agent_bindings or {}).items()}

    # Safety: max nodes * 2 iterations
    max_steps = max(len(nodes) * 2, 8)
    for _ in range(max_steps):
        node_id = run.current_node_id
        if not node_id or node_id not in nodes:
            run.status = "succeeded"
            run.current_node_id = None
            break

        node = nodes[node_id]
        ntype = (node.get("type") or "agent").lower()
        label = node.get("label") or node_id
        seq = len(run.steps)

        # Skip if this node already succeeded (resume after HITL)
        already = next(
            (s for s in run.steps if s.node_id == node_id and s.status == "succeeded"),
            None,
        )
        if already:
            nxt = _next_nodes(graph, node_id)
            run.current_node_id = nxt[0] if nxt else None
            if not nxt:
                run.status = "succeeded"
                break
            continue

        step = WorkflowStep(
            tenant_id=tenant_id,
            run_id=run.id,
            node_id=node_id,
            node_type=ntype,
            label=label,
            seq=seq,
            status="running",
            input_payload={},
        )
        db.add(step)
        run.steps.append(step)
        await db.flush()

        try:
            if ntype == "hitl":
                cfg = node.get("config") or {}
                keys = cfg.get("context_keys") or []
                preview = {k: context.get(k) for k in keys if k in context}
                step.input_payload = {
                    "message": cfg.get("message") or "Human approval required",
                    "preview": preview,
                }
                approval = ApprovalRequest(
                    tenant_id=tenant_id,
                    agent_id=None,
                    requested_by=actor_id,
                    action="workflow_hitl",
                    justification=cfg.get("message") or f"HITL gate: {label}",
                    payload={
                        "workflow_run_id": str(run.id),
                        "node_id": node_id,
                        "step_id": str(step.id),
                        "preview": preview,
                    },
                    status="pending",
                )
                db.add(approval)
                await db.flush()
                step.status = "awaiting_approval"
                step.approval_id = approval.id
                run.status = "awaiting_approval"
                run.pending_approval_id = approval.id
                run.current_node_id = node_id
                await db.flush()
                await record_audit(
                    db,
                    tenant_id=tenant_id,
                    action="workflow.hitl_waiting",
                    resource_type="workflow_run",
                    resource_id=str(run.id),
                    actor_id=actor_id,
                    actor_email=actor_email,
                    detail={"node_id": node_id, "approval_id": str(approval.id)},
                )
                break

            if ntype == "transform":
                cfg = node.get("config") or {}
                sets = cfg.get("set") or {}
                payload = {**sets, "from_context": {k: context.get(k) for k in list(context)[:8]}}
                # Optionally copy a node output under a new key
                if "from_node" in sets and sets["from_node"] in context:
                    payload["packaged"] = context[sets["from_node"]]
                step.input_payload = {"set": sets}
                step.output_payload = payload
                step.status = "succeeded"
                context[node_id] = payload
                context["last"] = payload

            elif ntype == "agent":
                agent = await _resolve_agent(
                    db, tenant_id=tenant_id, node=node, bindings=bindings
                )
                if agent is None:
                    raise ValueError(
                        f"No agent bound for node '{node_id}'. "
                        f"Bind an agent or register one in domain "
                        f"{(node.get('config') or {}).get('domain')}."
                    )
                agent_input = _build_agent_input(node, context, run.input_payload or {})
                skill_slug = (node.get("config") or {}).get("skill_slug")
                step.input_payload = agent_input
                step.agent_id = agent.id

                from app.services import execution as execution_service

                execution = await execution_service.invoke_agent(
                    db,
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    input_payload=agent_input,
                    config={},
                    actor_id=actor_id,
                    actor_email=actor_email,
                    skill_slug=skill_slug,
                )
                step.execution_id = execution.id
                step.latency_ms = execution.latency_ms
                if execution.status != "succeeded":
                    raise RuntimeError(execution.error or "Agent invoke failed")
                output = execution.response or {}
                step.output_payload = output
                step.status = "succeeded"
                context[node_id] = output
                context["last"] = output
                # Convenience aliases for common keys
                if isinstance(output, dict):
                    for key in ("stories", "summary", "risk", "cases", "root_cause"):
                        if key in output:
                            context[key] = output[key]

            else:
                raise ValueError(f"Unknown node type: {ntype}")

            await db.flush()
            nxt = _next_nodes(graph, node_id)
            if not nxt:
                run.status = "succeeded"
                run.current_node_id = None
                break
            run.current_node_id = nxt[0]
            run.status = "running"

        except Exception as exc:  # noqa: BLE001 — surface into run/step
            step.status = "failed"
            step.error = str(exc)
            run.status = "failed"
            run.error = str(exc)
            await db.flush()
            await record_audit(
                db,
                tenant_id=tenant_id,
                action="workflow.failed",
                resource_type="workflow_run",
                resource_id=str(run.id),
                actor_id=actor_id,
                actor_email=actor_email,
                detail={"node_id": node_id, "error": str(exc)},
            )
            break

    run.context = context
    await db.flush()

    if run.status == "succeeded":
        await record_audit(
            db,
            tenant_id=tenant_id,
            action="workflow.succeeded",
            resource_type="workflow_run",
            resource_id=str(run.id),
            actor_id=actor_id,
            actor_email=actor_email,
            detail={},
        )

    return await _load_run(db, run.id, tenant_id)


async def on_hitl_decided(
    db: AsyncSession,
    approval: ApprovalRequest,
    *,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> WorkflowRun | None:
    """Resume or fail a workflow when a HITL approval is decided."""
    if approval.action != "workflow_hitl":
        return None
    payload = approval.payload or {}
    run_id_raw = payload.get("workflow_run_id")
    if not run_id_raw:
        return None
    try:
        run_id = UUID(str(run_id_raw))
    except ValueError:
        return None

    run = await _load_run(db, run_id, approval.tenant_id)
    step_id_raw = payload.get("step_id")
    step = None
    if step_id_raw:
        try:
            step = await db.get(WorkflowStep, UUID(str(step_id_raw)))
        except ValueError:
            step = None
    if step is None:
        step = next(
            (s for s in run.steps if s.approval_id == approval.id),
            None,
        )

    if approval.status == "rejected":
        if step:
            step.status = "rejected"
            step.error = approval.decision_notes or "HITL rejected"
        run.status = "failed"
        run.error = approval.decision_notes or "Human rejected at HITL gate"
        run.pending_approval_id = None
        await db.flush()
        return await _load_run(db, run.id, approval.tenant_id)

    # approved
    if step:
        step.status = "succeeded"
        step.output_payload = {
            "decision": "approved",
            "notes": approval.decision_notes,
            "decided_by": str(approval.decided_by) if approval.decided_by else None,
        }
        ctx = dict(run.context or {})
        ctx[step.node_id] = step.output_payload
        ctx["last"] = step.output_payload
        run.context = ctx

    run.pending_approval_id = None
    run.status = "running"
    # Move to next node
    definition = run.definition or await db.get(WorkflowDefinition, run.definition_id)
    graph = (definition.graph if definition else {}) or {}
    node_id = payload.get("node_id") or run.current_node_id
    if node_id:
        nxt = _next_nodes(graph, node_id)
        run.current_node_id = nxt[0] if nxt else None
        if not nxt:
            run.status = "succeeded"
            await db.flush()
            return await _load_run(db, run.id, approval.tenant_id)

    await db.flush()
    return await advance_run(
        db,
        run_id=run.id,
        tenant_id=approval.tenant_id,
        actor_id=actor_id,
        actor_email=actor_email,
    )


def enrich_definition(defn: WorkflowDefinition) -> dict[str, Any]:
    graph = defn.graph or {}
    nodes = graph.get("nodes") or []
    hitl = sum(1 for n in nodes if isinstance(n, dict) and n.get("type") == "hitl")
    return {
        "node_count": len(nodes),
        "hitl_count": hitl,
    }
