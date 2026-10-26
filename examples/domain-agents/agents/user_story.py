"""AD — SDLC User Story authoring agent."""

from __future__ import annotations

from typing import Any

from agents._llm_json import invoke_json, provider_meta

AGENT_META = {
    "id": "ad-user-story",
    "name": "AD User Story Author",
    "framework": "langgraph",
    "domain": "AD",
    "capabilities": [
        "user_story_generation",
        "acceptance_criteria",
        "sdlc_backlog",
        "openai_llm",
    ],
    "description": (
        "Creates INVEST-ready user stories with acceptance criteria, "
        "edge cases, and story points from a feature brief."
    ),
}

SAMPLE_BRIEF = (
    "As a bank customer I need to reset my password from the mobile app "
    "using OTP, so I can regain access without calling support. "
    "Must comply with MFA policy and lock after 5 failed OTP attempts."
)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    brief = (
        payload.get("brief")
        or payload.get("feature")
        or payload.get("requirement")
        or payload.get("text")
        or ""
    ).strip()
    if payload.get("use_sample") or not brief:
        brief = SAMPLE_BRIEF

    persona = str(payload.get("persona") or "end user")
    project = str(payload.get("project") or "Digital Banking")

    data = invoke_json(
        system=(
            "You are a senior Business Analyst for Application Development (AD). "
            "Produce a single JSON object with keys: "
            "summary (string), "
            "title (string), "
            "user_story (string in 'As a… I want… So that…' form), "
            "acceptance_criteria (array of strings, Given/When/Then preferred), "
            "edge_cases (array of strings), "
            "non_functional (array of strings), "
            "story_points (integer fibonacci 1-13), "
            "priority (Must|Should|Could|Won't), "
            "dependencies (array of strings), "
            "open_questions (array of strings)."
        ),
        user=(
            f"Project: {project}\nPersona hint: {persona}\n\n"
            f"Feature brief:\n{brief}\n\nReturn JSON only."
        ),
    )

    output = {
        "agent_id": AGENT_META["id"],
        "domain": "AD",
        "task": "user_story",
        "summary": data.get("summary") or data.get("title") or "User story drafted",
        "title": data.get("title"),
        "user_story": data.get("user_story"),
        "acceptance_criteria": data.get("acceptance_criteria") or [],
        "edge_cases": data.get("edge_cases") or [],
        "non_functional": data.get("non_functional") or [],
        "story_points": data.get("story_points"),
        "priority": data.get("priority"),
        "dependencies": data.get("dependencies") or [],
        "open_questions": data.get("open_questions") or [],
        "issues": [],
        **provider_meta(),
    }
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": "Brief ingested", "node": "ingest"},
            {"role": "assistant", "content": "Story drafted", "node": "author"},
            {"role": "assistant", "content": "Acceptance criteria added", "node": "refine"},
        ],
        "metadata": {
            "nodes": ["ingest", "author", "refine"],
            "domain": "AD",
            **provider_meta(),
        },
    }
