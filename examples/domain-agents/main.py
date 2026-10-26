"""FastAPI surface for AD / AMS / QE domain LLM agents."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agents import AGENTS, list_agent_metas
from llm_config import deployment_or_model, llm_configured, llm_provider

app = FastAPI(
    title="TCS AI Harness — Domain Agents (AD / AMS / QE)",
    description="User stories, sprint planning, AMS incident analysis, QE test design",
    version="1.0.0",
)


class InvokeBody(BaseModel):
    input: Any = None
    agent_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


def _normalize(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"use_sample": True}
    if isinstance(raw, str):
        return {"text": raw, "brief": raw, "requirements": raw}
    if isinstance(raw, dict):
        return raw
    return {"value": raw}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "domain-agents",
        "agents": list(AGENTS.keys()),
        "openai_configured": llm_configured(),
        "llm_provider": llm_provider(),
        "model": deployment_or_model(),
    }


def _run_agent(agent_id: str, raw_input: Any) -> dict[str, Any]:
    entry = AGENTS.get(str(agent_id))
    if not entry:
        raise HTTPException(
            404,
            f"Unknown agent_id: {agent_id}. Known: {', '.join(AGENTS)}",
        )
    payload = _normalize(raw_input)
    started = time.perf_counter()
    try:
        result = entry["run"](payload)
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
    meta["agent_id"] = agent_id
    return {
        "output": result.get("output") or {},
        "messages": result.get("messages") or [],
        "metadata": meta,
        "usage": {},
        "run_id": meta["run_id"],
        "trace_id": meta["run_id"],
    }


@app.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    out = []
    for meta in list_agent_metas():
        aid = meta["id"]
        out.append(
            {
                "id": aid,
                "name": meta["name"],
                "framework": meta.get("framework", "langgraph"),
                "domain": meta.get("domain"),
                "capabilities": meta.get("capabilities", []),
                "description": meta.get("description"),
                # Per-agent URL so Harness can register each without agent_id in body
                "invoke_url": f"/agents/{aid}/invoke",
            }
        )
    return out


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    entry = AGENTS.get(agent_id)
    if not entry:
        raise HTTPException(404, f"Unknown agent_id: {agent_id}")
    meta = entry["meta"]
    return {
        **meta,
        "invoke_url": f"/agents/{agent_id}/invoke",
        "runs_url": f"/agents/{agent_id}/invoke",
    }


@app.post("/agents/{agent_id}/invoke")
def invoke_named(agent_id: str, body: InvokeBody) -> dict[str, Any]:
    return _run_agent(agent_id, body.input)


@app.post("/invoke")
def invoke(body: InvokeBody) -> dict[str, Any]:
    agent_id = body.agent_id
    payload = _normalize(body.input)
    if not agent_id and isinstance(payload, dict):
        agent_id = payload.pop("agent_id", None) or payload.pop("agent", None)
    if not agent_id:
        agent_id = "ad-user-story"
    return _run_agent(str(agent_id), payload)


@app.post("/runs")
def runs(body: InvokeBody) -> dict[str, Any]:
    return invoke(body)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8091")))
