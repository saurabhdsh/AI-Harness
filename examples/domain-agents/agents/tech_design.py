"""AD — SDLC technical design agent."""

from __future__ import annotations

from typing import Any

from agents._llm_json import invoke_json, provider_meta

AGENT_META = {
    "id": "ad-tech-design",
    "name": "AD Tech Design Author",
    "framework": "langgraph",
    "domain": "AD",
    "capabilities": [
        "technical_design",
        "architecture_sketch",
        "api_contract",
        "openai_llm",
    ],
    "description": (
        "Produces a lightweight technical design from a user story: "
        "components, APIs, data model, risks, and open questions."
    ),
}

SAMPLE = (
    "User story: As a bank customer I want to reset my password via OTP "
    "on mobile so I can regain access without calling support."
)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    story = (
        payload.get("user_story")
        or payload.get("brief")
        or payload.get("requirement")
        or payload.get("text")
        or ""
    ).strip()
    if payload.get("use_sample") or not story:
        story = SAMPLE
    stack = str(payload.get("stack") or "Java Spring Boot + React Native + Postgres")

    data = invoke_json(
        system=(
            "You are a senior Application Development (AD) solution designer. "
            "Return a single JSON object with keys: "
            "summary (string), "
            "components (array of {name, responsibility}), "
            "apis (array of {method, path, purpose}), "
            "data_model (array of {entity, fields}), "
            "sequence (array of strings describing happy-path steps), "
            "nfrs (array of strings), "
            "risks (array of strings), "
            "open_questions (array of strings)."
        ),
        user=f"Target stack: {stack}\n\nStory / brief:\n{story}\n\nReturn JSON only.",
    )

    output = {
        "agent_id": AGENT_META["id"],
        "domain": "AD",
        "task": "tech_design",
        "summary": data.get("summary") or "Technical design drafted",
        "components": data.get("components") or [],
        "apis": data.get("apis") or [],
        "data_model": data.get("data_model") or [],
        "sequence": data.get("sequence") or [],
        "nfrs": data.get("nfrs") or [],
        "risks": data.get("risks") or [],
        "open_questions": data.get("open_questions") or [],
        "issues": [],
        **provider_meta(),
    }
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": "Story analysed", "node": "ingest"},
            {"role": "assistant", "content": "Design sketched", "node": "design"},
            {"role": "assistant", "content": "Risks captured", "node": "review"},
        ],
        "metadata": {"nodes": ["ingest", "design", "review"], "domain": "AD", **provider_meta()},
    }
