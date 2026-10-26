"""Shared JSON LLM invoke helper (Azure-safe) with usage capture."""

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


def _usage_from_response(resp: Any) -> dict[str, int]:
    """Pull token counts from LangChain AIMessage metadata."""
    usage: dict[str, int] = {}
    meta = getattr(resp, "usage_metadata", None) or {}
    if isinstance(meta, dict) and meta:
        tin = meta.get("input_tokens") or meta.get("prompt_tokens") or 0
        tout = meta.get("output_tokens") or meta.get("completion_tokens") or 0
        total = meta.get("total_tokens") or (int(tin) + int(tout))
        usage = {
            "input_tokens": int(tin or 0),
            "output_tokens": int(tout or 0),
            "total_tokens": int(total or 0),
        }
    if not usage.get("input_tokens") and not usage.get("output_tokens"):
        rm = getattr(resp, "response_metadata", None) or {}
        tok = rm.get("token_usage") or rm.get("usage") or {}
        if isinstance(tok, dict):
            tin = tok.get("prompt_tokens") or tok.get("input_tokens") or 0
            tout = tok.get("completion_tokens") or tok.get("output_tokens") or 0
            usage = {
                "input_tokens": int(tin or 0),
                "output_tokens": int(tout or 0),
                "total_tokens": int(tok.get("total_tokens") or (int(tin or 0) + int(tout or 0))),
            }
    return usage


def invoke_json(system: str, user: str) -> tuple[dict[str, Any], dict[str, int]]:
    """Return (parsed_json, usage). Usage may be empty if the provider omits it."""
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
            return extract_json(text), _usage_from_response(resp)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"LLM JSON invoke failed: {last_error}")


def provider_meta() -> dict[str, str]:
    return {"model": deployment_or_model(), "llm_provider": llm_provider()}
