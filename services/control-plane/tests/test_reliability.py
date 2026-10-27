"""Reliability Center — aggregates from real executions."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient

from app.models.execution import AgentExecution
from app.services.reliability import classify_error


def test_classify_error():
    assert classify_error("Connection refused")[0] == "connection"
    assert classify_error("Read timeout after 30s")[0] == "timeout"
    assert classify_error("HTTP 503 from upstream")[0] == "http_5xx"
    assert classify_error("UnsupportedOperationError: deploy")[0] == "unsupported"
    assert classify_error(None)[0] == "unknown"


@pytest.mark.asyncio
async def test_reliability_overview(client: AsyncClient, session_factory, tenant_and_user):
    tenant, _user = tenant_and_user

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "flaky-agent",
            "framework": "generic_rest",
            "lifecycle_state": "registered",
            "invoke_url": "http://127.0.0.1:9/invoke",
            "domain": "AMS",
        },
    )
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    async with session_factory() as session:
        aid = UUID(agent_id)
        session.add(
            AgentExecution(
                tenant_id=tenant.id,
                agent_id=aid,
                status="succeeded",
                request={},
                response={"ok": True},
                latency_ms=120.0,
            )
        )
        session.add(
            AgentExecution(
                tenant_id=tenant.id,
                agent_id=aid,
                status="failed",
                request={},
                error="Connection refused to upstream",
                latency_ms=40.0,
            )
        )
        session.add(
            AgentExecution(
                tenant_id=tenant.id,
                agent_id=aid,
                status="failed",
                request={},
                error="Read timeout after 30s",
                latency_ms=30000.0,
            )
        )
        await session.commit()

    res = await client.get("/api/v1/reliability/overview?window_hours=24")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_executions"] >= 3
    assert body["failed"] >= 2
    assert body["error_rate"] > 0
    assert any(c["class_id"] == "connection" for c in body["error_classes"])
    assert any(a["agent_id"] == agent_id for a in body["agents_at_risk"])
    assert len(body["recent_failures"]) >= 2
    assert "synthetic" not in body["note"].lower() or "no synthetic" in body["note"].lower()
