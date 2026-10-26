"""FastAPI surface for the OpenAI-powered LangGraph AD agent."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from graph.agent import AGENT_META, run_agent
from llm_config import deployment_or_model, llm_configured, llm_provider

logger = logging.getLogger("ad_openai_agent")

app = FastAPI(
    title="TCS AI Harness — LangGraph OpenAI AD Agent",
    description="Real LangGraph StateGraph agent using OpenAI",
    version="1.0.0",
)


class InvokeBody(BaseModel):
    input: Any = None
    agent_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


def _normalize(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {"repo_snippet": raw, "task": "analyze"}
    if isinstance(raw, dict):
        return raw
    return {"value": raw}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "langgraph-openai-agent",
        "openai_configured": llm_configured(),
        "llm_provider": llm_provider(),
        "model": deployment_or_model(),
        "azure_endpoint_set": bool(os.getenv("AZURE_OPENAI_ENDPOINT")),
    }


@app.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    return [
        {
            "id": AGENT_META["id"],
            "name": AGENT_META["name"],
            "framework": AGENT_META["framework"],
            "capabilities": AGENT_META["capabilities"],
            "invoke_url": "/invoke",
        }
    ]


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    if agent_id != AGENT_META["id"]:
        raise HTTPException(404, f"Unknown agent_id: {agent_id}")
    return {**AGENT_META, "invoke_url": "/invoke", "runs_url": "/runs"}


@app.post("/invoke")
async def invoke(body: InvokeBody) -> dict[str, Any]:
    if body.agent_id and body.agent_id != AGENT_META["id"]:
        raise HTTPException(404, f"Unknown agent_id: {body.agent_id}")
    payload = _normalize(body.input)
    logger.info("invoke start task=%s keys=%s", payload.get("task"), sorted(payload.keys()))
    started = time.perf_counter()
    try:
        # Run sync LangGraph work off the event loop so /health stays responsive
        result = await asyncio.to_thread(run_agent, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Agent execution failed: {exc}") from exc

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    meta = dict(result.get("metadata") or {})
    meta["latency_ms"] = latency_ms
    meta["run_id"] = str(uuid.uuid4())
    usage = result.get("usage") or {}
    if not usage.get("input_tokens") and not usage.get("output_tokens"):
        import json as _json

        blob = _json.dumps(result.get("output") or {}, default=str)
        est_out = max(80, len(blob) // 4)
        est_in = max(60, est_out // 2)
        usage = {
            "input_tokens": est_in,
            "output_tokens": est_out,
            "total_tokens": est_in + est_out,
            "estimated": True,
        }
    logger.info(
        "invoke done latency_ms=%s tokens_in=%s tokens_out=%s",
        latency_ms,
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )
    return {
        "output": result.get("output") or {},
        "messages": result.get("messages") or [],
        "metadata": meta,
        "usage": usage,
        "run_id": meta["run_id"],
        "trace_id": meta["run_id"],
    }


@app.post("/runs")
async def runs(body: InvokeBody) -> dict[str, Any]:
    return await invoke(body)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8090")))
