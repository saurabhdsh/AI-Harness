"""AMS Incident Agent — digital twin simulator + optional proxy to rest-agent."""

from __future__ import annotations

import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="TCS AI Harness — AMS Incident Digital Twin",
    description=(
        "Emits synthetic AMS incidents via /twin/events and can forward "
        "analysis to the REST incident agent (or run inline rules)."
    ),
    version="1.0.0",
)

REST_AGENT_URL = os.environ.get("REST_AGENT_URL", "http://127.0.0.1:8082").rstrip("/")

# Synthetic incident templates for the digital twin
TWIN_TEMPLATES: list[dict[str, str]] = [
    {
        "title": "Payments API elevated error rate",
        "logs": "HTTP 500 from payments-svc; connection refused to payments-db:5432",
        "severity": "high",
        "service": "payments-svc",
    },
    {
        "title": "Checkout pod OOMKilled",
        "logs": "Out of memory: Kill process 1244 (python) score 900; heap space",
        "severity": "critical",
        "service": "checkout",
    },
    {
        "title": "Auth gateway unauthorized spike",
        "logs": "401 Unauthorized; token expired; authentication failure rate 12%",
        "severity": "medium",
        "service": "auth-gateway",
    },
    {
        "title": "Kafka consumer lag on orders",
        "logs": "consumer lag 450000 on topic orders.created; broker not available intermittently",
        "severity": "high",
        "service": "orders-consumer",
    },
    {
        "title": "TLS handshake failures to CDN origin",
        "logs": "SSL certificate verify failed; TLS handshake error after cert rotation",
        "severity": "high",
        "service": "edge-proxy",
    },
    {
        "title": "Disk pressure on log volume",
        "logs": "no space left on device; ENOSPC writing /var/log/app.log",
        "severity": "critical",
        "service": "log-shipper",
    },
]

# Simple in-memory event buffer
_EVENTS: list[dict[str, Any]] = []
_RNG = random.Random(42)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_one() -> dict[str, Any]:
    tmpl = _RNG.choice(TWIN_TEMPLATES)
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "source": "ams-digital-twin",
        "title": tmpl["title"],
        "logs": tmpl["logs"],
        "severity": tmpl["severity"],
        "service": tmpl["service"],
        "labels": {
            "env": _RNG.choice(["prod", "staging", "dr"]),
            "region": _RNG.choice(["us-east-1", "eu-west-1", "ap-south-1"]),
        },
    }
    _EVENTS.append(event)
    # Cap buffer
    if len(_EVENTS) > 200:
        del _EVENTS[:-200]
    return event


class InvokeBody(BaseModel):
    input: dict[str, Any] | str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None


def _inline_analyze(title: str, logs: str, severity: str) -> dict[str, Any]:
    """Fallback RCA if rest-agent is unreachable — mirrors rest-agent keywords lightly."""
    blob = f"{title}\n{logs}".lower()
    if "oom" in blob or "memory" in blob:
        hyp, rem = "Memory exhaustion", "Raise limits / fix leak"
    elif "connection refused" in blob or "timeout" in blob:
        hyp, rem = "Dependency connectivity", "Check network and dependency health"
    elif "401" in blob or "auth" in blob:
        hyp, rem = "Auth failure", "Refresh credentials / check IdP"
    elif "kafka" in blob or "lag" in blob:
        hyp, rem = "Messaging backlog", "Scale consumers / check brokers"
    elif "ssl" in blob or "tls" in blob or "certificate" in blob:
        hyp, rem = "TLS/certificate issue", "Renew certs / sync CA"
    elif "disk" in blob or "enospc" in blob or "no space" in blob:
        hyp, rem = "Disk full", "Free space / expand volume"
    else:
        hyp, rem = "Undetermined degradation", "Collect more signals"
    return {
        "incident": {"title": title, "severity": severity, "log_chars": len(logs)},
        "rca_hypotheses": [{"hypothesis": hyp, "confidence": 0.7}],
        "remediation_recommendations": [rem],
        "primary_hypothesis": hyp,
        "analysis_mode": "twin_inline",
    }


async def _forward_to_rest(title: str, logs: str, severity: str) -> dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{REST_AGENT_URL}/invoke",
                json={"input": {"title": title, "logs": logs, "severity": severity}},
            )
            if resp.status_code < 400:
                body = resp.json()
                out = body.get("output", body)
                if isinstance(out, dict):
                    out = {**out, "proxied_via": REST_AGENT_URL}
                return out if isinstance(out, dict) else {"value": out}
    except Exception:  # noqa: BLE001
        pass
    return _inline_analyze(title, logs, severity)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "ams-incident-agent",
        "rest_agent_url": REST_AGENT_URL,
        "buffered_events": len(_EVENTS),
    }


@app.get("/twin/events")
def twin_events(count: int = 1, seed: int | None = None) -> dict[str, Any]:
    """Emit synthetic AMS incidents (digital twin).

    Query params:
      count — number of new events to generate (1–20)
      seed  — optional RNG seed for reproducible demos
    """
    global _RNG
    if seed is not None:
        _RNG = random.Random(seed)
    n = max(1, min(count, 20))
    created = [_emit_one() for _ in range(n)]
    return {
        "generated": len(created),
        "events": created,
        "total_buffered": len(_EVENTS),
    }


@app.get("/twin/events/history")
def twin_history(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    return {"events": _EVENTS[-limit:], "total_buffered": len(_EVENTS)}


@app.post("/invoke")
async def invoke(body: InvokeBody) -> dict[str, Any]:
    """Analyze an incident — prefers rest-agent, falls back to inline rules.

    If input is empty / {"from_twin": true}, analyzes the latest twin event
    (emitting one if the buffer is empty).
    """
    started = time.perf_counter()
    raw = body.input
    if isinstance(raw, str):
        payload: dict[str, Any] = {"title": raw, "logs": raw}
    elif isinstance(raw, dict):
        payload = raw
    else:
        payload = {}

    if payload.get("from_twin") or (not payload.get("title") and not payload.get("logs")):
        if not _EVENTS:
            _emit_one()
        ev = _EVENTS[-1]
        title, logs, severity = ev["title"], ev["logs"], ev["severity"]
        twin_id = ev["id"]
    else:
        title = str(payload.get("title") or "")
        logs = str(payload.get("logs") or payload.get("log") or "")
        severity = str(payload.get("severity") or "medium")
        twin_id = None

    output = await _forward_to_rest(title, logs, severity)
    if twin_id:
        output["twin_event_id"] = twin_id

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "output": output,
        "messages": [
            {
                "role": "assistant",
                "content": output.get("primary_hypothesis", "Analyzed incident"),
            }
        ],
        "metadata": {
            "latency_ms": latency_ms,
            "model": output.get("analysis_mode", "ams-twin"),
            "run_id": str(uuid.uuid4()),
            "agent_id": body.agent_id or "ams-incident-twin",
            "rest_agent_url": REST_AGENT_URL,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8084")),
        reload=False,
    )
