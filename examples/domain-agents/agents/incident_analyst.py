"""AMS — incident triage / RCA analyst agent."""

from __future__ import annotations

from typing import Any

from agents._llm_json import invoke_json, provider_meta

AGENT_META = {
    "id": "ams-incident-analyst",
    "name": "AMS Incident Analyst",
    "framework": "langgraph",
    "domain": "AMS",
    "capabilities": [
        "incident_triage",
        "root_cause_analysis",
        "runbook_suggestions",
        "openai_llm",
    ],
    "description": (
        "Analyzes AMS production incidents from title/logs/metrics and "
        "returns severity, likely RCA, blast radius, and runbook steps."
    ),
}

SAMPLE = {
    "title": "Payments API elevated error rate",
    "service": "payments-svc",
    "severity_hint": "high",
    "logs": (
        "HTTP 500 from payments-svc; connection refused to payments-db:5432; "
        "pool exhausted; timeout after 30s"
    ),
    "metrics": "error_rate=18% p99=4200ms active_connections=200/200",
}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("use_sample"):
        payload = {**SAMPLE, **{k: v for k, v in payload.items() if k != "use_sample"}}

    title = str(payload.get("title") or payload.get("incident") or SAMPLE["title"])
    service = str(payload.get("service") or SAMPLE["service"])
    logs = str(payload.get("logs") or payload.get("description") or SAMPLE["logs"])
    metrics = str(payload.get("metrics") or SAMPLE["metrics"])
    severity_hint = str(payload.get("severity") or payload.get("severity_hint") or "unknown")

    data = invoke_json(
        system=(
            "You are an AMS (Application Management Services) L2/L3 incident analyst. "
            "Return JSON with keys: "
            "summary (string), "
            "severity (critical|high|medium|low), "
            "likely_root_cause (string), "
            "confidence (0-1 number), "
            "blast_radius (string), "
            "affected_services (array of strings), "
            "immediate_actions (array of strings), "
            "runbook_steps (array of strings), "
            "monitoring_checks (array of strings), "
            "escalation (string), "
            "issues (array of {code,severity,message})."
        ),
        user=(
            f"Title: {title}\nService: {service}\nSeverity hint: {severity_hint}\n"
            f"Logs:\n{logs}\n\nMetrics:\n{metrics}\n\nReturn JSON only."
        ),
    )

    output = {
        "agent_id": AGENT_META["id"],
        "domain": "AMS",
        "task": "incident_analysis",
        "summary": data.get("summary") or "Incident analysis complete",
        "severity": data.get("severity"),
        "likely_root_cause": data.get("likely_root_cause"),
        "confidence": data.get("confidence"),
        "blast_radius": data.get("blast_radius"),
        "affected_services": data.get("affected_services") or [service],
        "immediate_actions": data.get("immediate_actions") or [],
        "runbook_steps": data.get("runbook_steps") or [],
        "monitoring_checks": data.get("monitoring_checks") or [],
        "escalation": data.get("escalation"),
        "issues": data.get("issues") or [],
        **provider_meta(),
    }
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": "Signals collected", "node": "ingest"},
            {"role": "assistant", "content": "RCA hypothesized", "node": "analyze"},
            {"role": "assistant", "content": "Runbook drafted", "node": "remediate"},
        ],
        "metadata": {
            "nodes": ["ingest", "analyze", "remediate"],
            "domain": "AMS",
            **provider_meta(),
        },
    }
