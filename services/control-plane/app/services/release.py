"""Gated release trains — promote agents across environments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.approval import ApprovalRequest
from app.models.release import Promotion, ReleaseTrain
from app.schemas.release import PromotionCreate
from app.services.audit import record_audit

# Canonical ladder used by the default "standard" train
ENV_ORDER = ("dev", "staging", "prod")

DEFAULT_STAGES: list[dict[str, Any]] = [
    {"env": "dev", "gates": []},
    {
        "env": "staging",
        "gates": ["evaluation"],
        "approval_for_risk": ["high", "critical"],
    },
    {
        "env": "prod",
        "gates": ["evaluation", "approval"],
        "approval_for_risk": ["low", "medium", "high", "critical"],
    },
]

LIFECYCLE_FOR_ENV = {
    "dev": "registered",
    "staging": "validated",
    "prod": "production",
}


def _normalize_env(env: str) -> str:
    e = (env or "dev").strip().lower()
    aliases = {"production": "prod", "prd": "prod", "stage": "staging", "stg": "staging", "development": "dev"}
    return aliases.get(e, e)


async def ensure_default_train(db: AsyncSession, tenant_id: UUID) -> ReleaseTrain:
    result = await db.execute(
        select(ReleaseTrain).where(
            ReleaseTrain.tenant_id == tenant_id,
            ReleaseTrain.slug == "standard",
        )
    )
    train = result.scalar_one_or_none()
    if train:
        return train
    train = ReleaseTrain(
        tenant_id=tenant_id,
        name="Standard release train",
        slug="standard",
        description="dev → staging → prod with evaluation + approval gates",
        stages=DEFAULT_STAGES,
        is_default=True,
        is_active=True,
    )
    db.add(train)
    await db.flush()
    return train


def _stage_for_env(stages: list[dict[str, Any]], to_env: str) -> dict[str, Any] | None:
    for s in stages:
        if _normalize_env(str(s.get("env", ""))) == to_env:
            return s
    return None


def _allowed_transition(from_env: str, to_env: str, stages: list[dict[str, Any]]) -> tuple[bool, str]:
    if from_env == to_env:
        return False, f"Agent is already in {to_env}"
    envs = [_normalize_env(str(s.get("env", ""))) for s in stages if s.get("env")]
    if to_env not in envs:
        return False, f"Target env '{to_env}' is not on this train ({', '.join(envs)})"
    if from_env not in envs:
        # Allow onboarding strays into first stage only
        if to_env == envs[0]:
            return True, ""
        return False, f"Source env '{from_env}' is not on this train; promote to {envs[0]} first"
    fi, ti = envs.index(from_env), envs.index(to_env)
    if ti != fi + 1:
        return False, f"Must promote one stage at a time ({from_env} → {envs[fi + 1] if fi + 1 < len(envs) else '—'})"
    return True, ""


def _build_gates(
    agent: Agent,
    stage: dict[str, Any],
    *,
    require_evaluation: bool | None,
    require_approval: bool | None,
) -> list[dict[str, Any]]:
    stage_gates = list(stage.get("gates") or [])
    risk = (agent.risk_class or "medium").lower()
    approval_risks = [r.lower() for r in (stage.get("approval_for_risk") or [])]

    want_eval = "evaluation" in stage_gates if require_evaluation is None else require_evaluation
    want_approval = (
        ("approval" in stage_gates or risk in approval_risks)
        if require_approval is None
        else require_approval
    )

    gates: list[dict[str, Any]] = []
    if want_eval:
        passed = (agent.evaluation_status or "").lower() == "passed"
        gates.append(
            {
                "id": "evaluation",
                "type": "evaluation",
                "required": True,
                "status": "passed" if passed else "failed",
                "detail": (
                    f"evaluation_status={agent.evaluation_status}"
                    if passed
                    else "Latest evaluation must pass before promotion (run Evaluation Lab)"
                ),
            }
        )
    else:
        gates.append(
            {
                "id": "evaluation",
                "type": "evaluation",
                "required": False,
                "status": "skipped",
                "detail": "Evaluation gate not required for this stage",
            }
        )

    if want_approval:
        gates.append(
            {
                "id": "approval",
                "type": "approval",
                "required": True,
                "status": "pending",
                "detail": "Human approval required (Governance Center or Release Command)",
            }
        )
    else:
        gates.append(
            {
                "id": "approval",
                "type": "approval",
                "required": False,
                "status": "skipped",
                "detail": "Approval not required for this risk/stage",
            }
        )

    return gates


def _required_gates_ok(gates: list[dict[str, Any]], *, pending_ok: bool = False) -> tuple[bool, str | None]:
    for g in gates:
        if not g.get("required"):
            continue
        st = g.get("status")
        if st == "failed":
            return False, g.get("detail") or f"Gate {g.get('id')} failed"
        if st == "pending" and not pending_ok:
            return False, g.get("detail") or f"Gate {g.get('id')} pending"
        if st not in ("passed", "skipped", "pending"):
            return False, f"Gate {g.get('id')} in unexpected state {st}"
    return True, None


async def list_trains(db: AsyncSession, tenant_id: UUID) -> list[ReleaseTrain]:
    await ensure_default_train(db, tenant_id)
    result = await db.execute(
        select(ReleaseTrain)
        .where(ReleaseTrain.tenant_id == tenant_id, ReleaseTrain.is_active.is_(True))
        .order_by(ReleaseTrain.is_default.desc(), ReleaseTrain.name)
    )
    return list(result.scalars().all())


async def list_promotions(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    status: str | None = None,
    agent_id: UUID | None = None,
    limit: int = 100,
) -> list[Promotion]:
    q = select(Promotion).where(Promotion.tenant_id == tenant_id)
    if status:
        q = q.where(Promotion.status == status)
    if agent_id:
        q = q.where(Promotion.agent_id == agent_id)
    q = q.order_by(Promotion.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_promotion(db: AsyncSession, tenant_id: UUID, promotion_id: UUID) -> Promotion | None:
    promo = await db.get(Promotion, promotion_id)
    if promo is None or promo.tenant_id != tenant_id:
        return None
    return promo


async def create_promotion(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    user_email: str | None,
    data: PromotionCreate,
) -> Promotion:
    agent = await db.get(Agent, data.agent_id)
    if agent is None or agent.tenant_id != tenant_id:
        raise ValueError("Agent not found")

    to_env = _normalize_env(data.to_env)
    from_env = _normalize_env(agent.environment)

    trains = await list_trains(db, tenant_id)
    slug = (data.train_slug or "standard").strip().lower()
    train = next((t for t in trains if t.slug == slug), None) or next(
        (t for t in trains if t.is_default), trains[0]
    )

    ok, reason = _allowed_transition(from_env, to_env, list(train.stages or []))
    if not ok:
        raise ValueError(reason)

    stage = _stage_for_env(list(train.stages or []), to_env) or {}
    gates = _build_gates(
        agent,
        stage,
        require_evaluation=data.require_evaluation,
        require_approval=data.require_approval,
    )

    # Block immediately if a required non-approval gate failed
    hard_fail = next(
        (g for g in gates if g.get("required") and g.get("type") != "approval" and g.get("status") == "failed"),
        None,
    )
    if hard_fail:
        promo = Promotion(
            tenant_id=tenant_id,
            agent_id=agent.id,
            train_id=train.id,
            from_env=from_env,
            to_env=to_env,
            status="failed",
            gates=gates,
            justification=data.justification,
            error=hard_fail.get("detail") or "Gate failed",
            requested_by=user_id,
            metadata_={"train_slug": train.slug},
        )
        db.add(promo)
        await db.flush()
        await db.refresh(promo)
        await record_audit(
            db,
            tenant_id=tenant_id,
            action="release.promotion_failed",
            resource_type="promotion",
            resource_id=str(promo.id),
            actor_id=user_id,
            actor_email=user_email,
            detail={"from": from_env, "to": to_env, "error": promo.error},
        )
        return promo

    needs_approval = any(g.get("type") == "approval" and g.get("required") for g in gates)
    status = "awaiting_approval" if needs_approval else "promoting"

    promo = Promotion(
        tenant_id=tenant_id,
        agent_id=agent.id,
        train_id=train.id,
        from_env=from_env,
        to_env=to_env,
        status=status,
        gates=gates,
        justification=data.justification,
        requested_by=user_id,
        metadata_={"train_slug": train.slug, "agent_name": agent.name},
    )
    db.add(promo)
    await db.flush()

    if needs_approval:
        approval = ApprovalRequest(
            tenant_id=tenant_id,
            agent_id=agent.id,
            requested_by=user_id,
            action="promote",
            justification=data.justification
            or f"Promote {agent.name} {from_env} → {to_env}",
            payload={
                "promotion_id": str(promo.id),
                "from_env": from_env,
                "to_env": to_env,
                "train_slug": train.slug,
                "agent_name": agent.name,
            },
            status="pending",
        )
        db.add(approval)
        await db.flush()
        promo.approval_id = approval.id
        await db.flush()
        await db.refresh(promo)
        await record_audit(
            db,
            tenant_id=tenant_id,
            action="release.promotion_awaiting_approval",
            resource_type="promotion",
            resource_id=str(promo.id),
            actor_id=user_id,
            actor_email=user_email,
            detail={"from": from_env, "to": to_env, "approval_id": str(approval.id)},
        )
        return promo

    return await apply_promotion(
        db,
        promo,
        actor_id=user_id,
        actor_email=user_email,
    )


async def apply_promotion(
    db: AsyncSession,
    promo: Promotion,
    *,
    actor_id: UUID | None,
    actor_email: str | None,
) -> Promotion:
    if promo.status in ("completed", "rejected", "cancelled"):
        return promo

    agent = await db.get(Agent, promo.agent_id)
    if agent is None:
        promo.status = "failed"
        promo.error = "Agent no longer exists"
        await db.flush()
        return promo

    # Re-check evaluation if still required
    gates = list(promo.gates or [])
    for g in gates:
        if g.get("type") == "evaluation" and g.get("required"):
            if (agent.evaluation_status or "").lower() == "passed":
                g["status"] = "passed"
                g["detail"] = f"evaluation_status={agent.evaluation_status}"
            else:
                g["status"] = "failed"
                g["detail"] = "Evaluation must pass before promotion completes"
        if g.get("type") == "approval" and g.get("required") and g.get("status") == "pending":
            # Caller must mark approval passed before apply
            promo.gates = gates
            promo.status = "awaiting_approval"
            await db.flush()
            return promo

    promo.gates = gates
    ok, reason = _required_gates_ok(gates, pending_ok=False)
    if not ok:
        promo.status = "failed"
        promo.error = reason
        await db.flush()
        await record_audit(
            db,
            tenant_id=promo.tenant_id,
            action="release.promotion_failed",
            resource_type="promotion",
            resource_id=str(promo.id),
            actor_id=actor_id,
            actor_email=actor_email,
            detail={"error": reason},
        )
        return promo

    # Honest metadata promote (connectors do not support native deploy yet)
    agent.environment = promo.to_env
    agent.lifecycle_state = LIFECYCLE_FOR_ENV.get(promo.to_env, agent.lifecycle_state)
    meta = dict(agent.metadata_ or {})
    history = list(meta.get("promotion_history") or [])
    history.append(
        {
            "promotion_id": str(promo.id),
            "from": promo.from_env,
            "to": promo.to_env,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    meta["promotion_history"] = history[-20:]
    meta["last_promotion_id"] = str(promo.id)
    agent.metadata_ = meta

    promo.status = "completed"
    promo.error = None
    promo.completed_at = datetime.now(timezone.utc)
    promo_meta = dict(promo.metadata_ or {})
    promo_meta["deploy"] = "skipped"
    promo_meta["deploy_reason"] = (
        "Native platform deploy is not supported by current connectors; "
        "control-plane environment + lifecycle updated."
    )
    promo.metadata_ = promo_meta
    await db.flush()
    await db.refresh(promo)

    await record_audit(
        db,
        tenant_id=promo.tenant_id,
        action="release.promoted",
        resource_type="promotion",
        resource_id=str(promo.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={
            "agent_id": str(agent.id),
            "from": promo.from_env,
            "to": promo.to_env,
            "lifecycle_state": agent.lifecycle_state,
        },
    )
    return promo


async def on_approval_decided(
    db: AsyncSession,
    approval: ApprovalRequest,
    *,
    actor_id: UUID | None,
    actor_email: str | None,
) -> Promotion | None:
    """Side-effect hook: promote action approvals complete or reject promotions."""
    if approval.action != "promote":
        return None
    payload = approval.payload or {}
    promo_id = payload.get("promotion_id")
    if not promo_id:
        return None
    try:
        pid = UUID(str(promo_id))
    except ValueError:
        return None
    promo = await db.get(Promotion, pid)
    if promo is None or promo.tenant_id != approval.tenant_id:
        return None
    if promo.status in ("completed", "cancelled"):
        return promo

    gates = list(promo.gates or [])
    if approval.status == "rejected":
        for g in gates:
            if g.get("type") == "approval":
                g["status"] = "failed"
                g["detail"] = approval.decision_notes or "Promotion rejected"
        promo.gates = gates
        promo.status = "rejected"
        promo.error = approval.decision_notes or "Approval rejected"
        await db.flush()
        await db.refresh(promo)
        await record_audit(
            db,
            tenant_id=promo.tenant_id,
            action="release.promotion_rejected",
            resource_type="promotion",
            resource_id=str(promo.id),
            actor_id=actor_id,
            actor_email=actor_email,
            detail={},
        )
        return promo

    if approval.status == "approved":
        for g in gates:
            if g.get("type") == "approval":
                g["status"] = "passed"
                g["detail"] = approval.decision_notes or "Approved"
        promo.gates = gates
        promo.status = "promoting"
        await db.flush()
        return await apply_promotion(
            db,
            promo,
            actor_id=actor_id,
            actor_email=actor_email,
        )
    return promo


async def cancel_promotion(
    db: AsyncSession,
    promo: Promotion,
    *,
    actor_id: UUID | None,
    actor_email: str | None,
) -> Promotion:
    if promo.status in ("completed", "rejected", "cancelled"):
        raise ValueError(f"Cannot cancel promotion in status {promo.status}")
    promo.status = "cancelled"
    if promo.approval_id:
        approval = await db.get(ApprovalRequest, promo.approval_id)
        if approval and approval.status == "pending":
            approval.status = "rejected"
            approval.decision_notes = "Cancelled with promotion"
            approval.decided_by = actor_id
    await db.flush()
    await db.refresh(promo)
    await record_audit(
        db,
        tenant_id=promo.tenant_id,
        action="release.promotion_cancelled",
        resource_type="promotion",
        resource_id=str(promo.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={},
    )
    return promo


async def build_board(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    trains = await list_trains(db, tenant_id)
    agents_result = await db.execute(
        select(Agent).where(Agent.tenant_id == tenant_id).order_by(Agent.name)
    )
    agents = list(agents_result.scalars().all())
    open_promos = await list_promotions(db, tenant_id, limit=50)
    open_promos = [p for p in open_promos if p.status in ("gating", "awaiting_approval", "promoting")]

    # Prefer train stage order; include any orphan envs at the end
    stage_envs = [
        _normalize_env(str(s.get("env")))
        for t in trains if t.is_default
        for s in (t.stages or [])
        if s.get("env")
    ] or list(ENV_ORDER)
    seen = set(stage_envs)
    for a in agents:
        e = _normalize_env(a.environment)
        if e not in seen:
            stage_envs.append(e)
            seen.add(e)

    environments = []
    for env in stage_envs:
        bucket = [
            {
                "id": str(a.id),
                "name": a.name,
                "domain": a.domain,
                "lifecycle_state": a.lifecycle_state,
                "evaluation_status": a.evaluation_status,
                "risk_class": a.risk_class,
                "health_status": a.health_status,
            }
            for a in agents
            if _normalize_env(a.environment) == env
        ]
        environments.append({"environment": env, "agents": bucket})

    return {
        "environments": environments,
        "trains": trains,
        "open_promotions": open_promos,
        "agents_by_id": {str(a.id): a for a in agents},
        "trains_by_id": {str(t.id): t for t in trains},
    }
