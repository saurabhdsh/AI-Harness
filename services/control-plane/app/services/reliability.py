"""Reliability aggregates from real AgentExecution rows (no synthetic SLOs)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.execution import AgentExecution
from app.schemas.reliability import (
    AgentRisk,
    ErrorClassBucket,
    FailureEvent,
    LatencyOutlier,
    ReliabilityOverview,
    TimelineBucket,
)

# Order matters — first match wins
_ERROR_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("timeout", "Timeouts", re.compile(r"timeout|timed\s*out|deadline", re.I)),
    (
        "connection",
        "Connectivity",
        re.compile(r"connect|connection|refused|unreachable|dns|network|ssl|tls", re.I),
    ),
    ("http_5xx", "Upstream 5xx", re.compile(r"\b5\d{2}\b|server error|internal server", re.I)),
    ("http_4xx", "Upstream 4xx", re.compile(r"\b4\d{2}\b|not found|unauthorized|forbidden", re.I)),
    (
        "unsupported",
        "Unsupported op",
        re.compile(r"unsupported|not\s+implemented|501", re.I),
    ),
    ("auth", "Auth / credentials", re.compile(r"auth|credential|token|api[_ ]?key|401|403", re.I)),
    ("validation", "Payload / validation", re.compile(r"validat|json|schema|parse|type error", re.I)),
]


def classify_error(error: str | None) -> tuple[str, str]:
    text = (error or "").strip()
    if not text:
        return "unknown", "Unknown / empty"
    for class_id, label, pattern in _ERROR_PATTERNS:
        if pattern.search(text):
            return class_id, label
    return "other", "Other"


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = min(len(sorted_vals) - 1, max(0, int(round((p / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


async def reliability_overview(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    window_hours: int = 24,
    failure_limit: int = 40,
) -> ReliabilityOverview:
    window_hours = max(1, min(window_hours, 168 * 2))  # cap 14d
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)

    exec_rows = (
        await db.execute(
            select(AgentExecution)
            .where(
                AgentExecution.tenant_id == tenant_id,
                AgentExecution.created_at >= window_start,
            )
            .order_by(AgentExecution.created_at.desc())
            .limit(5000)
        )
    ).scalars().all()

    agents = (
        await db.execute(select(Agent).where(Agent.tenant_id == tenant_id))
    ).scalars().all()
    agent_by_id = {a.id: a for a in agents}

    unhealthy = sum(1 for a in agents if (a.health_status or "").lower() == "unhealthy")
    degraded = sum(1 for a in agents if (a.health_status or "").lower() == "degraded")

    succeeded = [e for e in exec_rows if e.status == "succeeded"]
    failed = [e for e in exec_rows if e.status == "failed"]
    running = [
        e for e in exec_rows if e.status in {"running", "pending"}
    ]
    total = len(exec_rows)
    success_rate = (len(succeeded) / total) if total else 0.0
    error_rate = (len(failed) / total) if total else 0.0

    latencies = sorted(
        float(e.latency_ms)
        for e in exec_rows
        if e.latency_ms is not None and e.latency_ms >= 0
    )
    avg_latency = (sum(latencies) / len(latencies)) if latencies else None
    p95 = _percentile(latencies, 95)
    max_lat = latencies[-1] if latencies else None

    # Error classes
    class_counts: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "label": "", "sample": None}
    )
    for e in failed:
        cid, label = classify_error(e.error)
        bucket = class_counts[cid]
        bucket["count"] += 1
        bucket["label"] = label
        if not bucket["sample"] and e.error:
            bucket["sample"] = (e.error or "")[:240]

    fail_n = max(len(failed), 1)
    error_classes = sorted(
        [
            ErrorClassBucket(
                class_id=cid,
                label=meta["label"],
                count=meta["count"],
                share=meta["count"] / fail_n if failed else 0.0,
                sample_error=meta["sample"],
            )
            for cid, meta in class_counts.items()
        ],
        key=lambda b: b.count,
        reverse=True,
    )

    # Per-agent risk
    by_agent: dict[UUID, list[AgentExecution]] = defaultdict(list)
    for e in exec_rows:
        by_agent[e.agent_id].append(e)

    agents_at_risk: list[AgentRisk] = []
    for agent_id, rows in by_agent.items():
        agent = agent_by_id.get(agent_id)
        fails = [r for r in rows if r.status == "failed"]
        oks = [r for r in rows if r.status == "succeeded"]
        if not fails and not oks:
            continue
        agent_lats = [
            float(r.latency_ms)
            for r in rows
            if r.latency_ms is not None
        ]
        last_fail = max(fails, key=lambda r: r.created_at) if fails else None
        err_rate = len(fails) / len(rows) if rows else 0.0
        # Surface agents with any failure, or elevated error rate
        if not fails and err_rate == 0:
            continue
        agents_at_risk.append(
            AgentRisk(
                agent_id=agent_id,
                agent_name=(agent.name if agent else str(agent_id)[:8]),
                domain=agent.domain if agent else None,
                health_status=(agent.health_status if agent else "unknown"),
                total=len(rows),
                failed=len(fails),
                succeeded=len(oks),
                error_rate=err_rate,
                avg_latency_ms=(sum(agent_lats) / len(agent_lats)) if agent_lats else None,
                last_failure_at=last_fail.created_at if last_fail else None,
                last_error=(last_fail.error[:240] if last_fail and last_fail.error else None),
            )
        )
    agents_at_risk.sort(key=lambda a: (a.error_rate, a.failed), reverse=True)

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # Timeline — 12 buckets across window
    slots = 12
    slot_seconds = max(60.0, (window_hours * 3600) / slots)
    timeline: list[TimelineBucket] = []
    for i in range(slots - 1, -1, -1):
        end = now - timedelta(seconds=i * slot_seconds)
        start = end - timedelta(seconds=slot_seconds)
        in_slot = [e for e in exec_rows if start <= _aware(e.created_at) < end]
        ok_n = sum(1 for e in in_slot if e.status == "succeeded")
        fail_n_slot = sum(1 for e in in_slot if e.status == "failed")
        timeline.append(
            TimelineBucket(
                t=end.astimezone().strftime("%H:%M"),
                start=start,
                ok=ok_n,
                fail=fail_n_slot,
                total=len(in_slot),
            )
        )

    recent_failures: list[FailureEvent] = []
    for e in failed[:failure_limit]:
        agent = agent_by_id.get(e.agent_id)
        cid, _ = classify_error(e.error)
        recent_failures.append(
            FailureEvent(
                execution_id=e.id,
                agent_id=e.agent_id,
                agent_name=(agent.name if agent else str(e.agent_id)[:8]),
                status=e.status,
                error=e.error,
                error_class=cid,
                latency_ms=e.latency_ms,
                created_at=e.created_at,
                trace_id=e.trace_id,
            )
        )

    # Latency outliers — top slowest with recorded latency (real, not SLO)
    with_lat = sorted(
        [e for e in exec_rows if e.latency_ms is not None],
        key=lambda e: float(e.latency_ms or 0),
        reverse=True,
    )[:12]
    latency_outliers: list[LatencyOutlier] = []
    for e in with_lat:
        agent = agent_by_id.get(e.agent_id)
        latency_outliers.append(
            LatencyOutlier(
                execution_id=e.id,
                agent_id=e.agent_id,
                agent_name=(agent.name if agent else str(e.agent_id)[:8]),
                status=e.status,
                latency_ms=float(e.latency_ms or 0),
                created_at=e.created_at,
            )
        )

    return ReliabilityOverview(
        window_hours=window_hours,
        window_start=window_start,
        generated_at=now,
        total_executions=total,
        succeeded=len(succeeded),
        failed=len(failed),
        running=len(running),
        success_rate=success_rate,
        error_rate=error_rate,
        avg_latency_ms=avg_latency,
        p95_latency_ms=p95,
        max_latency_ms=max_lat,
        agents_invoked=len(by_agent),
        unhealthy_agents=unhealthy,
        degraded_agents=degraded,
        error_classes=error_classes,
        agents_at_risk=agents_at_risk[:20],
        timeline=timeline,
        recent_failures=recent_failures,
        latency_outliers=latency_outliers,
        meta={"execution_sample": total, "cap": 5000},
    )
