"""Agent activity rollups — KEEL invokes + federated platform telemetry."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import UnsupportedOperationError
from app.connectors.registry import get_connector
from app.models.activity import AgentActivityDaily
from app.models.agent import Agent
from app.models.connection import PlatformConnection
from app.models.execution import AgentExecution
from app.schemas.activity import ActivityCollectResult, ActivityDayOut, AgentActivitySummary
from app.services.audit import record_audit


async def _upsert_day(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    day: date,
    source: str,
    sessions: int = 0,
    exceptions: int = 0,
    runtime_seconds: float = 0.0,
    unique_users: int = 0,
    tool_calls: int = 0,
    invocations: int = 0,
    metadata: dict | None = None,
    replace: bool = False,
) -> AgentActivityDaily:
    row = await db.scalar(
        select(AgentActivityDaily).where(
            AgentActivityDaily.tenant_id == tenant_id,
            AgentActivityDaily.agent_id == agent_id,
            AgentActivityDaily.day == day,
            AgentActivityDaily.source == source,
        )
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = AgentActivityDaily(
            tenant_id=tenant_id,
            agent_id=agent_id,
            day=day,
            source=source,
            sessions=sessions,
            exceptions=exceptions,
            runtime_seconds=runtime_seconds,
            unique_users=unique_users,
            tool_calls=tool_calls,
            invocations=invocations,
            metadata_=metadata or {},
            last_collected_at=now,
        )
        db.add(row)
    elif replace:
        row.sessions = sessions
        row.exceptions = exceptions
        row.runtime_seconds = runtime_seconds
        row.unique_users = unique_users
        row.tool_calls = tool_calls
        row.invocations = invocations
        if metadata is not None:
            row.metadata_ = metadata
        row.last_collected_at = now
    else:
        row.sessions += sessions
        row.exceptions += exceptions
        row.runtime_seconds += runtime_seconds
        row.unique_users = max(row.unique_users, unique_users)
        row.tool_calls += tool_calls
        row.invocations += invocations
        if metadata:
            merged = dict(row.metadata_ or {})
            merged.update(metadata)
            row.metadata_ = merged
        row.last_collected_at = now
    await db.flush()
    return row


async def record_keel_invocation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    status: str,
    latency_ms: float | None,
    invoked_by: UUID | None,
    tool_calls: int = 0,
) -> None:
    """Increment today's keel activity when control-plane invokes an agent."""
    day = datetime.now(timezone.utc).date()
    await _upsert_day(
        db,
        tenant_id=tenant_id,
        agent_id=agent_id,
        day=day,
        source="keel",
        sessions=1,
        exceptions=1 if status == "failed" else 0,
        runtime_seconds=(latency_ms or 0) / 1000.0,
        unique_users=1 if invoked_by else 0,
        tool_calls=tool_calls,
        invocations=1,
    )


async def rebuild_keel_activity_from_executions(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    days: int = 30,
) -> int:
    """Recompute keel source rows from AgentExecution (idempotent replace)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(AgentExecution).where(
                AgentExecution.tenant_id == tenant_id,
                AgentExecution.agent_id == agent_id,
                AgentExecution.created_at >= since,
            )
        )
    ).scalars().all()

    by_day: dict[date, dict[str, Any]] = {}
    for ex in rows:
        d = (ex.created_at or datetime.now(timezone.utc)).date()
        bucket = by_day.setdefault(
            d,
            {
                "sessions": 0,
                "exceptions": 0,
                "runtime_seconds": 0.0,
                "users": set(),
                "tool_calls": 0,
                "invocations": 0,
            },
        )
        bucket["sessions"] += 1
        bucket["invocations"] += 1
        if ex.status == "failed":
            bucket["exceptions"] += 1
        bucket["runtime_seconds"] += (ex.latency_ms or 0) / 1000.0
        if ex.invoked_by:
            bucket["users"].add(str(ex.invoked_by))
        # tool calls from response spans if present
        resp = ex.response or {}
        spans = resp.get("spans") if isinstance(resp, dict) else None
        if isinstance(spans, list):
            bucket["tool_calls"] += sum(
                1 for s in spans if isinstance(s, dict) and "tool" in str(s.get("name", "")).lower()
            )

    count = 0
    for d, b in by_day.items():
        await _upsert_day(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            day=d,
            source="keel",
            sessions=b["sessions"],
            exceptions=b["exceptions"],
            runtime_seconds=b["runtime_seconds"],
            unique_users=len(b["users"]),
            tool_calls=b["tool_calls"],
            invocations=b["invocations"],
            replace=True,
        )
        count += 1
    return count


async def collect_platform_telemetry(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    connection_id: UUID,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> ActivityCollectResult:
    """Pull get_telemetry from connected platform for all linked agents."""
    conn = await db.get(PlatformConnection, connection_id)
    if conn is None or conn.tenant_id != tenant_id:
        raise LookupError("Connection not found")
    if not conn.collect_observability:
        return ActivityCollectResult(
            connection_id=conn.id,
            status="skipped",
            detail={"reason": "collect_observability disabled"},
        )

    connector = get_connector(
        conn.connector_type, base_url=conn.base_url, secret_ref=conn.secret_ref
    )
    agents = (
        await db.execute(
            select(Agent).where(
                Agent.tenant_id == tenant_id,
                Agent.connection_id == conn.id,
            )
        )
    ).scalars().all()

    upserted = 0
    errors: list[str] = []
    today = datetime.now(timezone.utc).date()

    for agent in agents:
        if not agent.external_id:
            continue
        try:
            telem = await connector.get_telemetry(agent.external_id)
        except UnsupportedOperationError as exc:
            errors.append(f"{agent.external_id}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{agent.external_id}: {exc}")
            continue

        # Expected telem shape: sessions, exceptions, runtime_seconds, unique_users, tool_calls, days?
        days_payload = telem.get("daily") if isinstance(telem, dict) else None
        if isinstance(days_payload, list) and days_payload:
            for item in days_payload:
                if not isinstance(item, dict):
                    continue
                raw_day = item.get("day") or today.isoformat()
                try:
                    d = date.fromisoformat(str(raw_day)[:10])
                except ValueError:
                    d = today
                await _upsert_day(
                    db,
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    day=d,
                    source=conn.connector_type,
                    sessions=int(item.get("sessions") or 0),
                    exceptions=int(item.get("exceptions") or 0),
                    runtime_seconds=float(item.get("runtime_seconds") or 0),
                    unique_users=int(item.get("unique_users") or 0),
                    tool_calls=int(item.get("tool_calls") or 0),
                    invocations=int(item.get("invocations") or item.get("sessions") or 0),
                    metadata={"raw": item},
                    replace=True,
                )
                upserted += 1
        elif isinstance(telem, dict):
            await _upsert_day(
                db,
                tenant_id=tenant_id,
                agent_id=agent.id,
                day=today,
                source=conn.connector_type,
                sessions=int(telem.get("sessions") or 0),
                exceptions=int(telem.get("exceptions") or 0),
                runtime_seconds=float(telem.get("runtime_seconds") or 0),
                unique_users=int(telem.get("unique_users") or 0),
                tool_calls=int(telem.get("tool_calls") or 0),
                invocations=int(telem.get("invocations") or telem.get("sessions") or 0),
                metadata={"raw": telem},
                replace=True,
            )
            upserted += 1

        # Always refresh keel projection alongside federation
        await rebuild_keel_activity_from_executions(
            db, tenant_id=tenant_id, agent_id=agent.id, days=30
        )

    await record_audit(
        db,
        tenant_id=tenant_id,
        action="observability.collect",
        resource_type="platform_connection",
        resource_id=str(conn.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"upserted": upserted, "errors": errors[:10]},
    )
    return ActivityCollectResult(
        connection_id=conn.id,
        status="completed" if not errors else "partial",
        snapshots_upserted=upserted,
        detail={"errors": errors},
        error="; ".join(errors[:3]) if errors and not upserted else None,
    )


async def agent_activity_summary(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    window_days: int = 30,
) -> AgentActivitySummary:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != tenant_id:
        raise LookupError("Agent not found")

    # Ensure keel rollup is fresh
    await rebuild_keel_activity_from_executions(
        db, tenant_id=tenant_id, agent_id=agent_id, days=window_days
    )

    since = date.today() - timedelta(days=window_days)
    rows = (
        await db.execute(
            select(AgentActivityDaily)
            .where(
                AgentActivityDaily.tenant_id == tenant_id,
                AgentActivityDaily.agent_id == agent_id,
                AgentActivityDaily.day >= since,
            )
            .order_by(AgentActivityDaily.day.desc())
        )
    ).scalars().all()

    sessions = exceptions = tool_calls = invocations = 0
    runtime = 0.0
    users = 0
    by_source: dict[str, dict[str, float | int]] = {}
    for r in rows:
        sessions += r.sessions
        exceptions += r.exceptions
        runtime += r.runtime_seconds
        tool_calls += r.tool_calls
        invocations += r.invocations
        users = max(users, r.unique_users)  # rough; better sum unique across days is hard
        src = by_source.setdefault(
            r.source,
            {
                "sessions": 0,
                "exceptions": 0,
                "runtime_seconds": 0.0,
                "invocations": 0,
                "tool_calls": 0,
            },
        )
        src["sessions"] = int(src["sessions"]) + r.sessions
        src["exceptions"] = int(src["exceptions"]) + r.exceptions
        src["runtime_seconds"] = float(src["runtime_seconds"]) + r.runtime_seconds
        src["invocations"] = int(src["invocations"]) + r.invocations
        src["tool_calls"] = int(src["tool_calls"]) + r.tool_calls

    # Better unique users from executions
    since_dt = datetime.now(timezone.utc) - timedelta(days=window_days)
    user_count = await db.scalar(
        select(func.count(func.distinct(AgentExecution.invoked_by))).where(
            AgentExecution.tenant_id == tenant_id,
            AgentExecution.agent_id == agent_id,
            AgentExecution.created_at >= since_dt,
            AgentExecution.invoked_by.is_not(None),
        )
    )

    return AgentActivitySummary(
        agent_id=agent_id,
        window_days=window_days,
        sessions=sessions,
        exceptions=exceptions,
        runtime_seconds=runtime,
        runtime_hours=round(runtime / 3600.0, 4),
        unique_users=int(user_count or users or 0),
        tool_calls=tool_calls,
        invocations=invocations,
        by_source=by_source,
        daily=[ActivityDayOut.model_validate(r) for r in rows],
        note="Sessions approximate invocations when federated session IDs are unavailable.",
    )
