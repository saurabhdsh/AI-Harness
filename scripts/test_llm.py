#!/usr/bin/env python3
"""Smoke-test LLM credentials the same way as your other-Mac test_llm.py.

Usage (from repo root, with .env already filled):
  python3 scripts/test_llm.py
  # or
  cd examples/langgraph-openai-agent && ../.venv/...  # prefers Azure when set
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().strip("\r")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    _load_dotenv(root / ".env")
    _load_dotenv(root / "examples" / "langgraph-openai-agent" / ".env")

    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai_key = os.getenv("OPENAI_API_KEY")

    prompt = "Explain agentic AI in three simple bullet points."

    if azure_key and azure_endpoint:
        from openai import AzureOpenAI

        deployment = (
            os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("OPENAI_MODEL")
            or "gpt-5-mini"
        )
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        print("==> Using Azure OpenAI")
        print(f"    endpoint   = {azure_endpoint}")
        print(f"    api_version= {api_version}")
        print(f"    deployment = {deployment}")

        client = AzureOpenAI(
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
        )
        print("==> OK")
        print(response.choices[0].message.content)
        return 0

    if openai_key:
        from openai import OpenAI

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        print("==> Using OpenAI public API")
        print(f"    model = {model}")
        client = OpenAI(api_key=openai_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        print("==> OK")
        print(response.choices[0].message.content)
        return 0

    print(
        "FAIL: No credentials found.\n"
        "Set in .env either:\n"
        "  AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT "
        "(+ AZURE_OPENAI_DEPLOYMENT / OPENAI_MODEL)\n"
        "or OPENAI_API_KEY",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
