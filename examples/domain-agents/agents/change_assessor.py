"""AMS — change / CAB risk assessment agent."""

from __future__ import annotations

from typing import Any

from agents._llm_json import invoke_json, provider_meta

AGENT_META = {
    "id": "ams-change-assessor",
    "name": "AMS Change Assessor",
    "framework": "langgraph",
    "domain": "AMS",
    "capabilities": [
        "change_assessment",
        "cab_risk",
        "rollback_plan",
        "openai_llm",
    ],
    "description": (
        "Assesses AMS change requests for risk, impact, CAB readiness, "
        "and rollback recommendations."
    ),
}

SAMPLE = {
    "title": "Upgrade payments-db Postgres 14 → 16",
    "service": "payments-db",
    "window": "Sunday 02:00–04:00 IST",
    "description": (
        "Major version upgrade with brief read-only window. "
        "Replicas rebuilt; app connection string unchanged."
    ),
}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("use_sample"):
        payload = {**SAMPLE, **{k: v for k, v in payload.items() if k != "use_sample"}}
    title = str(payload.get("title") or payload.get("change") or "").strip()
    if not title:
        payload = {**SAMPLE, **payload}
        title = SAMPLE["title"]

    data = invoke_json(
        system=(
            "You are an AMS Change Manager / CAB advisor. "
            "Return JSON with keys: "
            "summary (string), "
            "risk_rating (Low|Medium|High|Critical), "
            "impact (string), "
            "affected_services (array of strings), "
            "pre_checks (array of strings), "
            "implementation_steps (array of strings), "
            "rollback_plan (array of strings), "
            "cab_recommendation (Approve|Approve with conditions|Defer|Reject), "
            "conditions (array of strings), "
            "open_questions (array of strings)."
        ),
        user=(
            f"Change title: {title}\n"
            f"Service: {payload.get('service', 'n/a')}\n"
            f"Window: {payload.get('window', 'n/a')}\n"
            f"Description: {payload.get('description') or payload.get('text') or 'n/a'}\n"
            "Return JSON only."
        ),
    )

    output = {
        "agent_id": AGENT_META["id"],
        "domain": "AMS",
        "task": "change_assessment",
        "summary": data.get("summary") or "Change assessed",
        "risk_rating": data.get("risk_rating"),
        "impact": data.get("impact"),
        "affected_services": data.get("affected_services") or [],
        "pre_checks": data.get("pre_checks") or [],
        "implementation_steps": data.get("implementation_steps") or [],
        "rollback_plan": data.get("rollback_plan") or [],
        "cab_recommendation": data.get("cab_recommendation"),
        "conditions": data.get("conditions") or [],
        "open_questions": data.get("open_questions") or [],
        "issues": [],
        **provider_meta(),
    }
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": "Change ingested", "node": "ingest"},
            {"role": "assistant", "content": "Risk scored", "node": "assess"},
            {"role": "assistant", "content": "CAB note ready", "node": "advise"},
        ],
        "metadata": {"nodes": ["ingest", "assess", "advise"], "domain": "AMS", **provider_meta()},
    }
