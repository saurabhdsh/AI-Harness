"""AMS-style REST incident agent — rule-based RCA and remediation."""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="TCS AI Harness — REST AMS Incident Agent",
    description="Rule-based incident RCA and remediation recommendations",
    version="1.0.0",
)

# Keyword → (hypothesis, remediation, confidence)
RULES: list[tuple[re.Pattern[str], str, str, float]] = [
    (
        re.compile(r"out\s*of\s*memory|oom|memory\s*limit|heap\s*space", re.I),
        "Process exhausted available memory (OOM / heap pressure)",
        "Increase memory limits, investigate leaks, restart affected pods, enable heap dumps",
        0.9,
    ),
    (
        re.compile(r"connection\s*refused|econnrefused|connect\s*timeout", re.I),
        "Downstream dependency unreachable (connection refused/timeout)",
        "Verify service discovery, network policies, dependency health; retry with backoff",
        0.88,
    ),
    (
        re.compile(r"timeout|timed\s*out|deadline\s*exceeded", re.I),
        "Request exceeded configured timeout / deadline",
        "Raise client timeouts cautiously; check dependency latency and circuit breakers",
        0.8,
    ),
    (
        re.compile(r"5\d{2}\b|internal\s*server\s*error|http\s*500", re.I),
        "Upstream returned 5xx — application or gateway error",
        "Inspect application logs, recent deploys; roll back if error rate spiked post-release",
        0.75,
    ),
    (
        re.compile(r"disk\s*(full|space)|no\s*space\s*left|enospc", re.I),
        "Disk space exhausted on host or volume",
        "Free disk, expand PVC, rotate logs, clear temp/cache directories",
        0.92,
    ),
    (
        re.compile(r"cpu\s*(throttl|saturat)|high\s*cpu|load\s*average", re.I),
        "CPU saturation / throttling on the workload",
        "Scale horizontally, raise CPU requests/limits, profile hot paths",
        0.78,
    ),
    (
        re.compile(r"auth(entication|orization)?\s*(fail|error)|unauthorized|401|403|forbidden", re.I),
        "Authentication or authorization failure",
        "Rotate/refresh credentials, verify RBAC and token expiry, check IdP status",
        0.85,
    ),
    (
        re.compile(r"ssl|tls|certificate|handshake", re.I),
        "TLS/SSL certificate or handshake problem",
        "Renew certificates, sync CA bundles, verify SNI and cipher compatibility",
        0.86,
    ),
    (
        re.compile(r"database|postgres|mysql|oracle|sql\s*exception|deadlock", re.I),
        "Database layer fault (connectivity, deadlock, or query failure)",
        "Check DB health, connection pool, locks; kill long transactions if safe",
        0.82,
    ),
    (
        re.compile(r"kafka|broker|consumer\s*lag|partition", re.I),
        "Messaging backlog or broker unavailability",
        "Inspect broker health, consumer group lag; scale consumers or rebalance",
        0.8,
    ),
    (
        re.compile(r"null\s*pointer|npe|attributeerror|typeerror|segfault", re.I),
        "Application defect (null/type error or crash)",
        "Identify stack frame from logs; hotfix or roll back; add guard + regression test",
        0.7,
    ),
    (
        re.compile(r"deploy|release|rollback|canary", re.I),
        "Incident correlated with a recent release / deploy event",
        "Compare with previous healthy revision; consider canary pause or rollback",
        0.65,
    ),
]


class IncidentInput(BaseModel):
    title: str = ""
    logs: str = ""
    severity: str = "medium"


class InvokeBody(BaseModel):
    input: IncidentInput | dict[str, Any] | str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None


def _as_incident(raw: Any) -> IncidentInput:
    if raw is None:
        return IncidentInput()
    if isinstance(raw, str):
        return IncidentInput(title=raw, logs=raw)
    if isinstance(raw, IncidentInput):
        return raw
    if isinstance(raw, dict):
        return IncidentInput(
            title=str(raw.get("title") or raw.get("summary") or ""),
            logs=str(raw.get("logs") or raw.get("log") or raw.get("message") or ""),
            severity=str(raw.get("severity") or "medium").lower(),
        )
    return IncidentInput(title=str(raw))


def analyze_incident(incident: IncidentInput) -> dict[str, Any]:
    blob = f"{incident.title}\n{incident.logs}"
    matches: list[dict[str, Any]] = []
    remediations: list[str] = []
    seen_hyp: set[str] = set()

    for pattern, hypothesis, remediation, confidence in RULES:
        if pattern.search(blob) and hypothesis not in seen_hyp:
            seen_hyp.add(hypothesis)
            matches.append(
                {
                    "hypothesis": hypothesis,
                    "confidence": confidence,
                    "matched_rule": pattern.pattern,
                }
            )
            remediations.append(remediation)

    if not matches:
        matches.append(
            {
                "hypothesis": "Insufficient signals — generic service degradation",
                "confidence": 0.35,
                "matched_rule": None,
            }
        )
        remediations.append(
            "Gather more logs/metrics; verify recent changes; escalate to on-call with timeline"
        )

    # Severity-weighted priority
    sev = incident.severity.lower()
    sev_weight = {"critical": 1.1, "high": 1.05, "medium": 1.0, "low": 0.9}.get(sev, 1.0)
    for m in matches:
        m["confidence"] = round(min(0.99, m["confidence"] * sev_weight), 3)

    matches.sort(key=lambda m: m["confidence"], reverse=True)

    return {
        "incident": {
            "title": incident.title,
            "severity": sev,
            "log_chars": len(incident.logs),
        },
        "rca_hypotheses": matches,
        "remediation_recommendations": remediations,
        "primary_hypothesis": matches[0]["hypothesis"],
        "analysis_mode": "rule_based",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rest-agent"}


@app.post("/invoke")
def invoke(body: InvokeBody) -> dict[str, Any]:
    started = time.perf_counter()
    incident = _as_incident(body.input)
    output = analyze_incident(incident)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": f"RCA: {output['primary_hypothesis']}"},
        ],
        "metadata": {
            "latency_ms": latency_ms,
            "model": "rule-based-keywords",
            "run_id": str(uuid.uuid4()),
            "agent_id": body.agent_id or "ams-incident",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8082")),
        reload=False,
    )
