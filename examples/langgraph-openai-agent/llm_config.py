"""LLM client factory — OpenAI public API or Azure OpenAI.

Matches the common Azure setup:
  AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION,
  deployment name via AZURE_OPENAI_DEPLOYMENT or OPENAI_MODEL (e.g. gpt-5-mini).
"""

from __future__ import annotations

import os
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


def build_chat_model(*, temperature: float = 0.1, json_mode: bool = True) -> Any:
    """Return LangChain chat model for the configured provider."""
    provider = llm_provider()
    model = deployment_or_model()
    kwargs: dict[str, Any] = {}
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

    if provider == "azure":
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=azure_api_version(),
            azure_deployment=model,
            temperature=temperature,
            **kwargs,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=temperature, **kwargs)

    raise RuntimeError(
        "No LLM credentials configured. Set OPENAI_API_KEY, or "
        "AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT "
        "(optional AZURE_OPENAI_API_VERSION, AZURE_OPENAI_DEPLOYMENT / OPENAI_MODEL)."
    )


def chat_completions_request_config() -> dict[str, Any]:
    """HTTP target for raw chat.completions (eval judge, etc.)."""
    provider = llm_provider()
    model = deployment_or_model()
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
            "body_model": model,
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
            "body_model": model,
        }
    raise RuntimeError("No LLM credentials configured for chat completions")
