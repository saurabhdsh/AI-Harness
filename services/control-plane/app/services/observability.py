"""Observability helpers — traces and mission aggregates from DB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import AgentActivityDaily
from app.models.agent import Agent
from app.models.approval import ApprovalRequest
from app.models.connection import PlatformConnection
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

    since_30d = datetime.now(timezone.utc) - timedelta(days=30)
    day_since = since_30d.date()

    active_users = await db.scalar(
        select(func.count(func.distinct(AgentExecution.invoked_by))).where(
            AgentExecution.tenant_id == tenant_id,
            AgentExecution.created_at >= since_30d,
            AgentExecution.invoked_by.is_not(None),
        )
    )
    # Runtime hours: sum of KEEL invoke latency + federated activity runtime
    keel_runtime_ms = await db.scalar(
        select(func.coalesce(func.sum(AgentExecution.latency_ms), 0.0)).where(
            AgentExecution.tenant_id == tenant_id,
            AgentExecution.created_at >= since_30d,
        )
    )
    fed_runtime = await db.scalar(
        select(func.coalesce(func.sum(AgentActivityDaily.runtime_seconds), 0.0)).where(
            AgentActivityDaily.tenant_id == tenant_id,
            AgentActivityDaily.day >= day_since,
            AgentActivityDaily.source != "keel",
        )
    )
    keel_hours = float(keel_runtime_ms or 0) / 3_600_000.0
    fed_hours = float(fed_runtime or 0) / 3600.0

    sessions_30d = await db.scalar(
        select(func.coalesce(func.sum(AgentActivityDaily.sessions), 0)).where(
            AgentActivityDaily.tenant_id == tenant_id,
            AgentActivityDaily.day >= day_since,
        )
    )
    # Fallback sessions ≈ executions if activity table empty
    if not sessions_30d:
        sessions_30d = await db.scalar(
            select(func.count())
            .select_from(AgentExecution)
            .where(
                AgentExecution.tenant_id == tenant_id,
                AgentExecution.created_at >= since_30d,
            )
        )
    exceptions_30d = await db.scalar(
        select(func.coalesce(func.sum(AgentActivityDaily.exceptions), 0)).where(
            AgentActivityDaily.tenant_id == tenant_id,
            AgentActivityDaily.day >= day_since,
        )
    )
    if not exceptions_30d:
        exceptions_30d = await db.scalar(
            select(func.count())
            .select_from(AgentExecution)
            .where(
                AgentExecution.tenant_id == tenant_id,
                AgentExecution.created_at >= since_30d,
                AgentExecution.status == "failed",
            )
        )

    no_owner = await db.scalar(
        select(func.count())
        .select_from(Agent)
        .where(
            Agent.tenant_id == tenant_id,
            (Agent.owner.is_(None)) | (Agent.owner == ""),
        )
    )

    conns = (
        await db.execute(
            select(PlatformConnection).where(PlatformConnection.tenant_id == tenant_id)
        )
    ).scalars().all()
    synced = [c for c in conns if c.last_synced_at is not None]
    registry_sync = {
        "connected_platforms": len(conns),
        "platforms_synced": len(synced),
        "collect_observability_enabled": sum(1 for c in conns if c.collect_observability),
        "platforms": [
            {
                "id": str(c.id),
                "name": c.name,
                "connector_type": c.connector_type,
                "last_synced_at": c.last_synced_at.isoformat() if c.last_synced_at else None,
                "last_sync_status": c.last_sync_status,
                "synced_agent_count": c.synced_agent_count,
                "collect_observability": c.collect_observability,
            }
            for c in conns
        ],
    }

    return MissionOverview(
        total_agents=total_agents,
        by_lifecycle=by_lifecycle,
        by_health=by_health,
        by_evaluation=by_evaluation,
        recent_executions=int(recent.scalar_one() or 0),
        failed_executions_24h=int(failed.scalar_one() or 0),
        pending_approvals=int(pending.scalar_one() or 0),
        total_cost_usd=float(cost.scalar_one() or 0.0),
        active_users_30d=int(active_users or 0),
        agent_runtime_hours_30d=round(keel_hours + fed_hours, 4),
        registry_sync=registry_sync,
        agents_without_owners=int(no_owner or 0),
        sessions_30d=int(sessions_30d or 0),
        exceptions_30d=int(exceptions_30d or 0),
    )
