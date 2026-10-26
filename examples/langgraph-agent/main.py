"""LangGraph-style AD Code Engineering Agent — offline-capable FastAPI service."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from analyzer import analyze_code

APP_DIR = Path(__file__).resolve().parent
SAMPLE_SNIPPET = APP_DIR / "sample_repo" / "snippet.py"

AGENTS = [
    {
        "id": "ad-code-engineering",
        "name": "AD Code Engineering Agent",
        "framework": "langgraph",
        "capabilities": [
            "code_analysis",
            "complexity_hints",
            "unified_diff_patches",
            "offline_deterministic",
        ],
        "description": (
            "Analyzes or improves code snippets via a simplified LangGraph-style "
            "pipeline (parse → analyze → optionally patch). Works offline without API keys."
        ),
    }
]

DEFAULT_AGENT_ID = AGENTS[0]["id"]

app = FastAPI(
    title="TCS AI Harness — LangGraph Reference Agent",
    description="AD Code Engineering Agent (LangGraph-style invoke/runs)",
    version="1.0.0",
)


class InvokeBody(BaseModel):
    input: Any = None
    agent_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


def _normalize_input(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {"repo_snippet": raw, "task": "analyze"}
    if isinstance(raw, dict):
        return raw
    return {"value": raw}


def _resolve_snippet(payload: dict[str, Any]) -> str:
    snippet = (
        payload.get("repo_snippet")
        or payload.get("code")
        or payload.get("snippet")
        or payload.get("source")
    )
    if snippet:
        return str(snippet)
    # Demo convenience: load sample if requested
    if payload.get("use_sample") or payload.get("sample"):
        if SAMPLE_SNIPPET.exists():
            return SAMPLE_SNIPPET.read_text(encoding="utf-8")
    raise HTTPException(
        status_code=400,
        detail="Missing repo_snippet (or set use_sample=true for sample_repo/snippet.py)",
    )


def _optional_llm_note(result_summary: str) -> str | None:
    """Optional enhancement only when OPENAI_API_KEY is set — never required."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    # Soft enhancement path: we do not call the network by default even with key,
    # unless ENABLE_LLM=1 — keeps demos deterministic and offline-safe.
    if os.environ.get("ENABLE_LLM", "").lower() not in ("1", "true", "yes"):
        return (
            "OPENAI_API_KEY detected; set ENABLE_LLM=1 to enable optional narrative "
            f"enrichment. Deterministic analysis used: {result_summary[:80]}"
        )
    try:
        import json
        import urllib.request

        body = json.dumps(
            {
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {
                        "role": "system",
                        "content": "Summarize code review findings in 2 sentences.",
                    },
                    {"role": "user", "content": result_summary},
                ],
                "max_tokens": 120,
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 — optional path must never fail the agent
        return f"LLM enrichment skipped ({type(exc).__name__}); deterministic result retained."


def run_agent(payload: dict[str, Any], agent_id: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    aid = agent_id or payload.get("agent_id") or DEFAULT_AGENT_ID
    if aid not in {a["id"] for a in AGENTS}:
        raise HTTPException(status_code=404, detail=f"Unknown agent_id: {aid}")

    task = str(payload.get("task") or "analyze").lower()
    instruction = str(payload.get("instruction") or "")
    snippet = _resolve_snippet(payload)

    # Simplified graph steps (LangGraph-style message trail)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "AD Code Engineering graph started", "node": "start"},
        {
            "role": "assistant",
            "content": f"Routing task={task}",
            "node": "router",
        },
        {
            "role": "assistant",
            "content": f"Analyzing {len(snippet)} chars of source",
            "node": "analyze",
        },
    ]

    result = analyze_code(snippet, task=task, instruction=instruction)
    output = result.to_dict()
    output["agent_id"] = aid
    output["task"] = task

    llm_note = _optional_llm_note(result.summary)
    if llm_note:
        output["llm_enrichment"] = llm_note
        messages.append(
            {"role": "assistant", "content": "Optional LLM note attached", "node": "enrich"}
        )

    if task == "improve":
        messages.append(
            {
                "role": "assistant",
                "content": "Generated proposed_patch unified diff",
                "node": "patch",
            }
        )

    messages.append(
        {"role": "assistant", "content": result.summary, "node": "end"}
    )

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    model = "deterministic-ast" if result.language == "python" else "deterministic-heuristic"
    if llm_note and os.environ.get("ENABLE_LLM"):
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini") + "+deterministic"

    return {
        "output": output,
        "messages": messages,
        "metadata": {
            "latency_ms": latency_ms,
            "model": model,
            "agent_id": aid,
            "run_id": str(uuid.uuid4()),
            "framework": "langgraph",
            "offline": not bool(os.environ.get("ENABLE_LLM")),
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "langgraph-agent"}


@app.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "framework": a["framework"],
            "capabilities": a["capabilities"],
        }
        for a in AGENTS
    ]


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    for a in AGENTS:
        if a["id"] == agent_id:
            return {
                **a,
                "invoke_url": "/invoke",
                "runs_url": "/runs",
            }
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@app.post("/invoke")
def invoke(body: InvokeBody) -> dict[str, Any]:
    payload = _normalize_input(body.input)
    return run_agent(payload, body.agent_id)


@app.post("/runs")
def runs(body: InvokeBody) -> dict[str, Any]:
    """LangGraph-style alias for /invoke."""
    return invoke(body)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        reload=False,
    )
