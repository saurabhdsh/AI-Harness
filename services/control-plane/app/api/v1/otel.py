"""OpenTelemetry ingest — Agent 365–style first-party observability path."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import AuthUser, DbSession
from app.models.agent import Agent
from app.models.execution import AgentExecution, AgentTrace
from app.services import activity as activity_service
from app.services.audit import record_audit

router = APIRouter()


class OtelIngestResult(BaseModel):
    accepted_spans: int = 0
    executions_created: int = 0
    agent_id: UUID | None = None
    execution_id: UUID | None = None
    status: str = "ok"
    detail: dict[str, Any] = Field(default_factory=dict)


def _attr_map(attrs: list | dict | None) -> dict[str, Any]:
    if isinstance(attrs, dict):
        return attrs
    out: dict[str, Any] = {}
    if not isinstance(attrs, list):
        return out
    for a in attrs:
        if not isinstance(a, dict):
            continue
        key = a.get("key")
        val = a.get("value") or {}
        if isinstance(val, dict):
            for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
                if k in val:
                    out[str(key)] = val[k]
                    break
        elif key is not None:
            out[str(key)] = val
    return out


@router.post("/v1/traces", response_model=OtelIngestResult)
async def ingest_otlp_traces(
    body: dict[str, Any],
    db: DbSession,
    user: AuthUser,
) -> OtelIngestResult:
    """Accept OTLP/JSON TraceService ExportTraceServiceRequest-ish payloads.

    Looks for gen_ai.agent.id / microsoft.a365.agent.platform.id / resource agent name
    to bind spans to a registry agent. Creates an AgentExecution + AgentTrace.
    """
    resource_spans = body.get("resourceSpans") or body.get("resource_spans") or []
    if not resource_spans and "spans" in body:
        # Convenience: flat {spans, agent_external_id}
        resource_spans = [{"scopeSpans": [{"spans": body["spans"]}]}]

    flat_spans: list[dict[str, Any]] = []
    resource_attrs: dict[str, Any] = {}
    for rs in resource_spans:
        if not isinstance(rs, dict):
            continue
        resource_attrs.update(_attr_map((rs.get("resource") or {}).get("attributes")))
        for ss in rs.get("scopeSpans") or rs.get("scope_spans") or []:
            if not isinstance(ss, dict):
                continue
            for sp in ss.get("spans") or []:
                if isinstance(sp, dict):
                    flat_spans.append(sp)

    if not flat_spans:
        raise HTTPException(status_code=400, detail="No spans in OTLP payload")

    # Resolve agent
    ext = (
        body.get("agent_external_id")
        or resource_attrs.get("gen_ai.agent.id")
        or resource_attrs.get("microsoft.a365.agent.platform.id")
        or resource_attrs.get("agent.id")
    )
    name_hint = resource_attrs.get("gen_ai.agent.name") or resource_attrs.get("service.name")
    agent: Agent | None = None
    if ext:
        agent = await db.scalar(
            select(Agent).where(
                Agent.tenant_id == user.tenant_id,
                Agent.external_id == str(ext),
            )
        )
    if agent is None and name_hint:
        agent = await db.scalar(
            select(Agent).where(
                Agent.tenant_id == user.tenant_id,
                Agent.name == str(name_hint),
            )
        )
    if agent is None:
        # Auto-register draft from OTel so inventory stays complete
        agent = Agent(
            tenant_id=user.tenant_id,
            name=str(name_hint or ext or f"otel-agent-{uuid4().hex[:8]}"),
            platform="otel",
            framework="otel",
            external_id=str(ext) if ext else f"otel-{uuid4().hex[:12]}",
            lifecycle_state="registered",
            metadata_={"source": "otel_ingest"},
        )
        db.add(agent)
        await db.flush()

    # Find root invoke_agent / first span
    def span_name(s: dict) -> str:
        return str(s.get("name") or "")

    root = next((s for s in flat_spans if "invoke" in span_name(s).lower()), flat_spans[0])
    attrs = _attr_map(root.get("attributes"))
    status_code = (root.get("status") or {}).get("code") or root.get("statusCode") or "UNSET"
    failed = str(status_code).upper() in {"ERROR", "STATUS_CODE_ERROR", "2"}
    # duration
    start = int(root.get("startTimeUnixNano") or root.get("start_time_unix_nano") or 0)
    end = int(root.get("endTimeUnixNano") or root.get("end_time_unix_nano") or 0)
    latency_ms = (end - start) / 1_000_000.0 if end > start else None

    harness_spans = []
    for s in flat_spans:
        s_attrs = _attr_map(s.get("attributes"))
        s_start = int(s.get("startTimeUnixNano") or s.get("start_time_unix_nano") or 0)
        s_end = int(s.get("endTimeUnixNano") or s.get("end_time_unix_nano") or 0)
        harness_spans.append(
            {
                "name": span_name(s),
                "duration_ms": (s_end - s_start) / 1_000_000.0 if s_end > s_start else None,
                "attributes": s_attrs,
                "status": (s.get("status") or {}).get("code"),
            }
        )

    execution = AgentExecution(
        tenant_id=user.tenant_id,
        agent_id=agent.id,
        status="failed" if failed else "succeeded",
        request={"source": "otel", "attributes": attrs},
        response={"spans": harness_spans, "otlp": True},
        latency_ms=latency_ms,
        trace_id=str(root.get("traceId") or root.get("trace_id") or uuid4()),
        error=str((root.get("status") or {}).get("message") or "") if failed else None,
        invoked_by=user.user_id,
    )
    db.add(execution)
    await db.flush()
    db.add(
        AgentTrace(
            tenant_id=user.tenant_id,
            execution_id=execution.id,
            spans=harness_spans,
            status="error" if failed else "recorded",
        )
    )
    tool_n = sum(1 for s in harness_spans if "tool" in str(s.get("name", "")).lower())
    await activity_service.record_keel_invocation(
        db,
        tenant_id=user.tenant_id,
        agent_id=agent.id,
        status=execution.status,
        latency_ms=latency_ms,
        invoked_by=user.user_id,
        tool_calls=tool_n,
    )
    # Tag activity source as otel for today
    from datetime import date

    await activity_service._upsert_day(
        db,
        tenant_id=user.tenant_id,
        agent_id=agent.id,
        day=date.today(),
        source="otel",
        sessions=1,
        exceptions=1 if failed else 0,
        runtime_seconds=(latency_ms or 0) / 1000.0,
        unique_users=1,
        tool_calls=tool_n,
        invocations=1,
        metadata={"trace_id": execution.trace_id},
    )
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="otel.traces_ingested",
        resource_type="agent",
        resource_id=str(agent.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"spans": len(flat_spans), "execution_id": str(execution.id)},
    )
    return OtelIngestResult(
        accepted_spans=len(flat_spans),
        executions_created=1,
        agent_id=agent.id,
        execution_id=execution.id,
        status="ok",
    )


@router.get("/agents/{agent_id}/export")
async def export_agent_otel(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    limit: int = 20,
) -> dict[str, Any]:
    """Export recent KEEL traces as OTLP/JSON-ish resourceSpans for SIEM bridging."""
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    execs = (
        await db.execute(
            select(AgentExecution)
            .where(
                AgentExecution.tenant_id == user.tenant_id,
                AgentExecution.agent_id == agent_id,
            )
            .order_by(AgentExecution.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    spans_out: list[dict[str, Any]] = []
    for ex in execs:
        traces = (
            await db.execute(
                select(AgentTrace).where(
                    AgentTrace.execution_id == ex.id,
                    AgentTrace.tenant_id == user.tenant_id,
                )
            )
        ).scalars().all()
        for tr in traces:
            for sp in tr.spans or []:
                if not isinstance(sp, dict):
                    continue
                dur = sp.get("duration_ms") or ex.latency_ms or 0
                start_ns = int(
                    (ex.created_at or datetime.now(timezone.utc)).timestamp() * 1_000_000_000
                )
                end_ns = start_ns + int(float(dur) * 1_000_000)
                spans_out.append(
                    {
                        "name": sp.get("name") or "keel.span",
                        "traceId": ex.trace_id or str(ex.id),
                        "startTimeUnixNano": str(start_ns),
                        "endTimeUnixNano": str(end_ns),
                        "attributes": [
                            {"key": "gen_ai.agent.id", "value": {"stringValue": agent.external_id or str(agent.id)}},
                            {"key": "gen_ai.agent.name", "value": {"stringValue": agent.name}},
                            {"key": "keel.execution_id", "value": {"stringValue": str(ex.id)}},
                            {"key": "keel.status", "value": {"stringValue": ex.status}},
                        ],
                        "status": {
                            "code": "ERROR" if ex.status == "failed" else "OK",
                            "message": ex.error or "",
                        },
                    }
                )

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "keel-control-plane"}},
                        {
                            "key": "gen_ai.agent.id",
                            "value": {"stringValue": agent.external_id or str(agent.id)},
                        },
                    ]
                },
                "scopeSpans": [{"spans": spans_out}],
            }
        ]
    }
