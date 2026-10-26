"""AD — SDLC sprint / backlog planning agent."""

from __future__ import annotations

from typing import Any

from agents._llm_json import invoke_json, provider_meta

AGENT_META = {
    "id": "ad-sprint-planner",
    "name": "AD Sprint Planner",
    "framework": "langgraph",
    "domain": "AD",
    "capabilities": [
        "sprint_planning",
        "backlog_grooming",
        "capacity_planning",
        "openai_llm",
    ],
    "description": (
        "Turns a backlog of stories into a sprint plan with capacity, "
        "risks, and suggested sequencing."
    ),
}

SAMPLE_BACKLOG = [
    {"title": "Password reset OTP flow", "points": 5, "priority": "Must"},
    {"title": "OTP lockout + audit trail", "points": 3, "priority": "Must"},
    {"title": "Push notification on reset", "points": 2, "priority": "Should"},
    {"title": "Admin reset override", "points": 5, "priority": "Could"},
    {"title": "Analytics dashboard widget", "points": 8, "priority": "Won't"},
]


def run(payload: dict[str, Any]) -> dict[str, Any]:
    backlog = payload.get("backlog") or payload.get("stories")
    if payload.get("use_sample") or not backlog:
        backlog = SAMPLE_BACKLOG
    capacity = int(payload.get("capacity_points") or payload.get("capacity") or 20)
    sprint_name = str(payload.get("sprint") or "Sprint 14")
    team = str(payload.get("team") or "AD Squad Alpha")

    data, usage = invoke_json(
        system=(
            "You are an experienced AD Scrum Master / Tech Lead. "
            "Return JSON with keys: "
            "summary (string), "
            "sprint_goal (string), "
            "committed (array of {title, points, rationale}), "
            "deferred (array of {title, reason}), "
            "total_committed_points (int), "
            "capacity_points (int), "
            "utilization_pct (number), "
            "risks (array of strings), "
            "dependencies (array of strings), "
            "ceremonies (array of {name, when})."
        ),
        user=(
            f"Team: {team}\nSprint: {sprint_name}\nCapacity points: {capacity}\n"
            f"Backlog JSON:\n{backlog}\n\nReturn JSON only."
        ),
    )

    output = {
        "agent_id": AGENT_META["id"],
        "domain": "AD",
        "task": "sprint_plan",
        "summary": data.get("summary") or "Sprint plan ready",
        "sprint_goal": data.get("sprint_goal"),
        "committed": data.get("committed") or [],
        "deferred": data.get("deferred") or [],
        "total_committed_points": data.get("total_committed_points"),
        "capacity_points": data.get("capacity_points") or capacity,
        "utilization_pct": data.get("utilization_pct"),
        "risks": data.get("risks") or [],
        "dependencies": data.get("dependencies") or [],
        "ceremonies": data.get("ceremonies") or [],
        "issues": [],
        **provider_meta(),
    }
    return {
        "output": output,
        "messages": [
            {"role": "assistant", "content": "Backlog loaded", "node": "ingest"},
            {"role": "assistant", "content": "Capacity applied", "node": "capacity"},
            {"role": "assistant", "content": "Sprint committed", "node": "plan"},
        ],
        "usage": usage,
        "metadata": {
            "nodes": ["ingest", "capacity", "plan"],
            "domain": "AD",
            **provider_meta(),
        },
    }
