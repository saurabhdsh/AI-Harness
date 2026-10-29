"""Real agent invocation via connectors — never silently mock failures."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import InvokeRequest, UnsupportedOperationError
from app.connectors.registry import get_connector
from app.models.agent import Agent
from app.models.connection import PlatformConnection
from app.models.cost import CostRecord
from app.models.execution import AgentExecution, AgentTrace
from app.services import activity as activity_service
from app.services.audit import record_audit


def _connector_for_agent(agent: Agent, connection: PlatformConnection | None):
    if connection is not None:
        return get_connector(
            connection.connector_type,
            base_url=connection.base_url,
            secret_ref=connection.secret_ref,
        )
    # Direct invoke_url without connection — use framework hint
    if not agent.invoke_url:
        raise ValueError("Agent has no invoke_url and no platform connection")
    base = agent.invoke_url.rsplit("/", 1)[0] if "/" in agent.invoke_url else agent.invoke_url
    ctype = agent.framework if agent.framework in ("langgraph", "generic_rest", "rest") else "generic_rest"
    return get_connector(ctype, base_url=base, secret_ref=None)


async def invoke_agent(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    input_payload: dict,
    config: dict | None = None,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
    skill_slug: str | None = None,
) -> AgentExecution:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != tenant_id:
        raise LookupError("Agent not found")

    connection: PlatformConnection | None = None
    if agent.connection_id:
        connection = await db.get(PlatformConnection, agent.connection_id)

    # Inject attached enterprise skills into config + input
    from app.skills.service import format_skills_system_block, get_agent_skills_payload

    cfg = dict(config or {})
    slug = skill_slug or cfg.pop("skill_slug", None)
    if isinstance(input_payload, dict):
        slug = slug or input_payload.get("_skill_slug") or input_payload.get("skill_slug")
    skills = await get_agent_skills_payload(
        db, tenant_id=tenant_id, agent_id=agent_id, skill_slug=slug
    )
    enriched_input = dict(input_payload or {})
    if skills:
        system_block = format_skills_system_block(skills)
        cfg["skills"] = [
            {
                "slug": s["slug"],
                "name": s["name"],
                "version": s["version"],
                "domain": s["domain"],
                "instructions": s["instructions"],
                "output_schema": s.get("output_schema") or {},
                "attachment_config": s.get("attachment_config") or {},
            }
            for s in skills
        ]
        cfg["system_skills"] = system_block
        enriched_input["harness_skills"] = [
            {
                "slug": s["slug"],
                "name": s["name"],
                "instructions": s["instructions"],
                "output_schema": s.get("output_schema") or {},
            }
            for s in skills
        ]

    execution = AgentExecution(
        tenant_id=tenant_id,
        agent_id=agent.id,
        status="running",
        request={
            "input": enriched_input,
            "config": cfg,
            "skills": [s["slug"] for s in skills],
        },
        invoked_by=actor_id,
        trace_id=str(uuid4()),
    )
    db.add(execution)
    await db.flush()

    try:
        connector = _connector_for_agent(agent, connection)
        response = await connector.invoke_agent(
            InvokeRequest(
                input=enriched_input,
                config=cfg,
                external_id=agent.external_id,
                invoke_url=agent.invoke_url,
            )
        )
        execution.status = "succeeded"
        execution.response = response.output
        execution.latency_ms = response.latency_ms
        execution.token_input = response.token_input
        execution.token_output = response.token_output
        if response.trace_id:
            execution.trace_id = response.trace_id
        agent.health_status = "healthy"

        spans = [
            {
                "name": "connector.invoke",
                "status": "ok",
                "latency_ms": response.latency_ms,
                "connector": getattr(connector, "connector_type", "unknown"),
            }
        ]
        if response.raw.get("spans"):
            spans.extend(response.raw["spans"])

        trace = AgentTrace(
            tenant_id=tenant_id,
            execution_id=execution.id,
            spans=spans,
            status="ok",
        )
        db.add(trace)

        # Record cost from provider usage, or estimate from output when agents omit tokens
        from app.services.costing import compute_cost_usd, resolve_tokens

        tin, tout, estimated = resolve_tokens(
            token_input=response.token_input,
            token_output=response.token_output,
            output_payload=response.output,
        )
        execution.token_input = tin
        execution.token_output = tout
        cost_usd = compute_cost_usd(tin, tout)
        model_name = None
        if isinstance(response.output, dict):
            model_name = response.output.get("model")
        if not model_name and isinstance(response.raw, dict):
            raw_meta = response.raw.get("metadata")
            if isinstance(raw_meta, dict):
                model_name = raw_meta.get("model")
        if not model_name:
            model_name = (agent.metadata_ or {}).get("model")
        db.add(
            CostRecord(
                tenant_id=tenant_id,
                agent_id=agent.id,
                execution_id=execution.id,
                cost_usd=cost_usd,
                token_input=tin,
                token_output=tout,
                model_name=str(model_name) if model_name else None,
                metadata_={
                    "source": "execution",
                    "rate_source": "placeholder",
                    "tokens_estimated": estimated,
                    "latency_ms": response.latency_ms,
                    "note": "Estimated rates — not provider invoices",
                },
            )
        )
    except UnsupportedOperationError:
        # Re-raise typed unsupported — caller surfaces it; mark execution failed
        execution.status = "failed"
        execution.error = "UnsupportedOperationError"
        agent.health_status = "degraded"
        await db.flush()
        raise
    except Exception as exc:
        execution.status = "failed"
        execution.error = str(exc)
        agent.health_status = "unhealthy"
        db.add(
            AgentTrace(
                tenant_id=tenant_id,
                execution_id=execution.id,
                spans=[{"name": "connector.invoke", "status": "error", "error": str(exc)}],
                status="error",
            )
        )
        await record_audit(
            db,
            tenant_id=tenant_id,
            action="agent.invoke.failed",
            resource_type="agent",
            resource_id=str(agent.id),
            actor_id=actor_id,
            actor_email=actor_email,
            detail={"execution_id": str(execution.id), "error": str(exc)},
        )
        await activity_service.record_keel_invocation(
            db,
            tenant_id=tenant_id,
            agent_id=agent.id,
            status=execution.status,
            latency_ms=execution.latency_ms,
            invoked_by=actor_id,
        )
        await db.flush()
        # Do not swallow — return failed execution so API can respond with real error details
        return execution

    await record_audit(
        db,
        tenant_id=tenant_id,
        action="agent.invoked",
        resource_type="agent",
        resource_id=str(agent.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"execution_id": str(execution.id), "status": execution.status},
    )
    tool_n = 0
    if isinstance(execution.response, dict):
        spans = execution.response.get("spans")
        if isinstance(spans, list):
            tool_n = sum(
                1 for s in spans if isinstance(s, dict) and "tool" in str(s.get("name", "")).lower()
            )
    await activity_service.record_keel_invocation(
        db,
        tenant_id=tenant_id,
        agent_id=agent.id,
        status=execution.status,
        latency_ms=execution.latency_ms,
        invoked_by=actor_id,
        tool_calls=tool_n,
    )
    await db.flush()
    return execution


async def list_executions(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentExecution]:
    stmt = (
        select(AgentExecution)
        .where(AgentExecution.tenant_id == tenant_id)
        .order_by(AgentExecution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if agent_id:
        stmt = stmt.where(AgentExecution.agent_id == agent_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_execution(
    db: AsyncSession, *, tenant_id: UUID, execution_id: UUID
) -> AgentExecution:
    execution = await db.get(AgentExecution, execution_id)
    if execution is None or execution.tenant_id != tenant_id:
        raise LookupError("Execution not found")
    return execution
