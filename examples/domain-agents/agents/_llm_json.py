"""Shared JSON LLM invoke helper (Azure-safe)."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from llm_config import build_chat_model, deployment_or_model, llm_configured, llm_provider


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError("LLM did not return parseable JSON")


def invoke_json(system: str, user: str) -> dict[str, Any]:
    if not llm_configured():
        raise RuntimeError(
            "No LLM credentials — set AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT "
            "or OPENAI_API_KEY"
        )
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            llm = build_chat_model(json_mode=False if attempt else None)
            resp = llm.invoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=user if attempt == 0 else f"{user}\nReturn JSON only."),
                ]
            )
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            return extract_json(text)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"LLM JSON invoke failed: {last_error}")


def provider_meta() -> dict[str, str]:
    return {"model": deployment_or_model(), "llm_provider": llm_provider()}
