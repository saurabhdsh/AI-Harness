"""QE — test design / case generation agent."""

from __future__ import annotations

from typing import Any

from agents._llm_json import invoke_json, provider_meta

AGENT_META = {
    "id": "qe-test-designer",
    "name": "QE Test Designer",
    "framework": "langgraph",
    "domain": "QE",
    "capabilities": [
        "test_case_design",
        "traceability",
        "risk_based_testing",
        "openai_llm",
    ],
    "description": (
        "Designs QE test suites from requirements or user stories with "
        "positive/negative cases, data, and risk tags."
    ),
}

SAMPLE_REQ = (
    "Password reset via OTP on mobile:\n"
    "- User requests reset with registered mobile number\n"
    "- OTP valid for 5 minutes, max 5 attempts\n"
    "- On success, user sets new password meeting complexity policy\n"
    "- Audit every attempt"
)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    requirements = (
        payload.get("requirements")
        or payload.get("user_story")
        or payload.get("brief")
        or payload.get("text")
        or ""
    ).strip()
    if payload.get("use_sample") or not requirements:
        requirements = SAMPLE_REQ

    level = str(payload.get("level") or payload.get("test_level") or "system")
    focus = str(payload.get("focus") or "functional,security")

    data, usage = invoke_json(
        system=(
            "You are a senior QE test designer. "
            "Return JSON with keys: "
            "summary (string), "
            "test_suite_name (string), "
            "coverage_notes (string), "
            "test_cases (array of {"
            "id, title, type (positive|negative|edge|security|performance), "
            "priority (P0|P1|P2|P3), preconditions (array), steps (array), "
            "expected_result (string), test_data (object), requirement_ref (string)}), "
            "risks (array of strings), "
            "automation_candidates (array of test case ids), "
            "issues (array of {code,severity,message})."
        ),
        user=(
            f"Test level: {level}\nFocus: {focus}\n\n"
            f"Requirements / story:\n{requirements}\n\nReturn JSON only."
        ),
    )

    cases = data.get("test_cases") or []
    output = {
        "agent_id": AGENT_META["id"],
        "domain": "QE",
        "task": "test_design",
        "summary": data.get("summary") or f"Designed {len(cases)} test cases",
        "test_suite_name": data.get("test_suite_name"),
        "coverage_notes": data.get("coverage_notes"),
        "test_cases": cases,
        "risks": data.get("risks") or [],
        "automation_candidates": data.get("automation_candidates") or [],
        "issues": data.get("issues") or [],
        "metrics": {"test_case_count": len(cases)},
        **provider_meta(),
    }
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": "Requirements parsed", "node": "ingest"},
            {"role": "assistant", "content": "Cases designed", "node": "design"},
            {"role": "assistant", "content": "Risk tagged", "node": "prioritize"},
        ],
        "usage": usage,
        "metadata": {
            "nodes": ["ingest", "design", "prioritize"],
            "domain": "QE",
            **provider_meta(),
        },
    }
