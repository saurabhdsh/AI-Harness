"""Observability helpers — traces and mission aggregates from DB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.approval import ApprovalRequest
from app.models.cost import CostRecord
from app.models.execution import AgentExecution, AgentTrace
from app.schemas.mission import MissionOverview


async def get_trace(
    db: AsyncSession, *, tenant_id: UUID, trace_id: UUID
) -> AgentTrace:
    # Accept either AgentTrace.id or look up by execution.trace_id string
    trace = await db.get(AgentTrace, trace_id)
    if trace is not None and trace.tenant_id == tenant_id:
        return trace

    # Fallback: treat path param as execution id
    stmt = (
        select(AgentTrace)
        .where(AgentTrace.execution_id == trace_id, AgentTrace.tenant_id == tenant_id)
        .order_by(AgentTrace.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    trace = result.scalar_one_or_none()
    if trace is None:
        raise LookupError("Trace not found")
    return trace


async def mission_overview(db: AsyncSession, *, tenant_id: UUID) -> MissionOverview:
    # Lifecycle counts
    life_rows = await db.execute(
        select(Agent.lifecycle_state, func.count())
        .where(Agent.tenant_id == tenant_id)
        .group_by(Agent.lifecycle_state)
    )
    by_lifecycle = {row[0]: row[1] for row in life_rows.all()}

    health_rows = await db.execute(
        select(Agent.health_status, func.count())
        .where(Agent.tenant_id == tenant_id)
        .group_by(Agent.health_status)
    )
    by_health = {row[0]: row[1] for row in health_rows.all()}

    eval_rows = await db.execute(
        select(Agent.evaluation_status, func.count())
        .where(Agent.tenant_id == tenant_id)
        .group_by(Agent.evaluation_status)
    )
    by_evaluation = {row[0]: row[1] for row in eval_rows.all()}

    total_agents = sum(by_lifecycle.values())

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = await db.execute(
        select(func.count())
        .select_from(AgentExecution)
        .where(AgentExecution.tenant_id == tenant_id, AgentExecution.created_at >= since)
    )
    failed = await db.execute(
        select(func.count())
        .select_from(AgentExecution)
        .where(
            AgentExecution.tenant_id == tenant_id,
            AgentExecution.created_at >= since,
            AgentExecution.status == "failed",
        )
    )
    pending = await db.execute(
        select(func.count())
        .select_from(ApprovalRequest)
        .where(
            ApprovalRequest.tenant_id == tenant_id,
            ApprovalRequest.status == "pending",
        )
    )
    cost = await db.execute(
        select(func.coalesce(func.sum(CostRecord.cost_usd), 0.0)).where(
            CostRecord.tenant_id == tenant_id
        )
    )

    return MissionOverview(
        total_agents=total_agents,
        by_lifecycle=by_lifecycle,
        by_health=by_health,
        by_evaluation=by_evaluation,
        recent_executions=int(recent.scalar_one() or 0),
        failed_executions_24h=int(failed.scalar_one() or 0),
        pending_approvals=int(pending.scalar_one() or 0),
        total_cost_usd=float(cost.scalar_one() or 0.0),
    )
