"""LLM HTTP client config — OpenAI or Azure OpenAI (same env as other Mac)."""

from __future__ import annotations

import os
import re
from typing import Any


def llm_provider() -> str:
    if os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
        return "azure"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "none"


def llm_configured() -> bool:
    return llm_provider() != "none"


def deployment_or_model() -> str:
    return (
        os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or os.getenv("OPENAI_MODEL")
        or ("gpt-5-mini" if llm_provider() == "azure" else "gpt-4o-mini")
    )


def azure_api_version() -> str:
    return os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")


def _is_restricted_model(name: str) -> bool:
    n = name.lower()
    return bool(re.search(r"(gpt-5|o1|o3|o4)", n))


def chat_completions_request_config() -> dict[str, Any]:
    provider = llm_provider()
    model = deployment_or_model()
    restricted = _is_restricted_model(model) or provider == "azure"
    if provider == "azure":
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        version = azure_api_version()
        url = (
            f"{endpoint}/openai/deployments/{model}/chat/completions"
            f"?api-version={version}"
        )
        return {
            "provider": "azure",
            "url": url,
            "headers": {
                "api-key": os.environ["AZURE_OPENAI_API_KEY"],
                "Content-Type": "application/json",
            },
            "model": model,
            "supports_json_object": not restricted,
            "supports_temperature": not restricted,
        }
    if provider == "openai":
        return {
            "provider": "openai",
            "url": "https://api.openai.com/v1/chat/completions",
            "headers": {
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            "model": model,
            "supports_json_object": True,
            "supports_temperature": True,
        }
    raise RuntimeError(
        "No LLM credentials. Set OPENAI_API_KEY or "
        "AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT"
    )
