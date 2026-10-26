"""QE — defect triage / severity classification agent."""

from __future__ import annotations

from typing import Any

from agents._llm_json import invoke_json, provider_meta

AGENT_META = {
    "id": "qe-defect-triage",
    "name": "QE Defect Triage",
    "framework": "langgraph",
    "domain": "QE",
    "capabilities": [
        "defect_triage",
        "severity_classification",
        "root_cause_hint",
        "openai_llm",
    ],
    "description": (
        "Triages QE defects: severity/priority, duplicate hints, "
        "repro gaps, and suggested next actions."
    ),
}

SAMPLE = {
    "title": "OTP expires immediately after request",
    "steps": "1) Request reset 2) Enter OTP within 30s 3) App shows 'OTP expired'",
    "expected": "OTP valid for 5 minutes",
    "actual": "Expired within seconds",
    "environment": "UAT / iOS 18",
}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("use_sample"):
        payload = {**SAMPLE, **{k: v for k, v in payload.items() if k != "use_sample"}}
    title = str(payload.get("title") or payload.get("defect") or "").strip()
    if not title:
        payload = {**SAMPLE, **payload}
        title = SAMPLE["title"]

    data, usage = invoke_json(
        system=(
            "You are a senior QE lead performing defect triage. "
            "Return JSON with keys: "
            "summary (string), "
            "severity (Blocker|Critical|Major|Minor|Trivial), "
            "priority (P1|P2|P3|P4), "
            "category (Functional|Performance|Security|Usability|Data|Environment), "
            "likely_area (string), "
            "repro_gaps (array of strings), "
            "suggested_tests (array of strings), "
            "next_actions (array of strings), "
            "duplicate_hint (string or null)."
        ),
        user=(
            f"Title: {title}\n"
            f"Steps: {payload.get('steps') or payload.get('text') or 'n/a'}\n"
            f"Expected: {payload.get('expected', 'n/a')}\n"
            f"Actual: {payload.get('actual', 'n/a')}\n"
            f"Environment: {payload.get('environment', 'n/a')}\n"
            "Return JSON only."
        ),
    )

    output = {
        "agent_id": AGENT_META["id"],
        "domain": "QE",
        "task": "defect_triage",
        "summary": data.get("summary") or "Defect triaged",
        "severity": data.get("severity"),
        "priority": data.get("priority"),
        "category": data.get("category"),
        "likely_area": data.get("likely_area"),
        "repro_gaps": data.get("repro_gaps") or [],
        "suggested_tests": data.get("suggested_tests") or [],
        "next_actions": data.get("next_actions") or [],
        "duplicate_hint": data.get("duplicate_hint"),
        "issues": [],
        **provider_meta(),
    }
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": "Defect ingested", "node": "ingest"},
            {"role": "assistant", "content": "Severity assigned", "node": "classify"},
            {"role": "assistant", "content": "Actions proposed", "node": "advise"},
        ],
        "usage": usage,
        "metadata": {"nodes": ["ingest", "classify", "advise"], "domain": "QE", **provider_meta()},
    }
