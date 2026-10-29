"""Tests: agent activity, mission hero metrics, OTel ingest."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_agent_activity_after_invoke(client: AsyncClient):
    create = await client.post(
        "/api/v1/agents",
        json={
            "name": "activity-agent",
            "framework": "langgraph",
            "invoke_url": "http://fake-agent:8080/invoke",
            "lifecycle_state": "registered",
            "owner": "qa",
        },
    )
    assert create.status_code == 201, create.text
    agent_id = create.json()["id"]

    import httpx

    mock_response = httpx.Response(
        200,
        json={"output": {"ok": True}, "usage": {"input_tokens": 1, "output_tokens": 1}},
    )

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            return mock_response

    with patch("httpx.AsyncClient", _Client):
        inv = await client.post(
            f"/api/v1/agents/{agent_id}/invoke",
            json={"input": {"message": "ping"}},
        )
    assert inv.status_code == 200, inv.text

    act = await client.get(f"/api/v1/agents/{agent_id}/activity?window_days=30")
    assert act.status_code == 200, act.text
    body = act.json()
    assert body["agent_id"] == agent_id
    assert body["sessions"] >= 1 or body["invocations"] >= 1
    assert body["runtime_hours"] >= 0


@pytest.mark.asyncio
async def test_mission_overview_heroes(client: AsyncClient):
    await client.post(
        "/api/v1/agents",
        json={
            "name": "hero-agent",
            "framework": "langgraph",
            "lifecycle_state": "registered",
            "owner": "ops",
        },
    )
    conn = await client.post(
        "/api/v1/connectors",
        json={
            "name": "Hero Platform",
            "connector_type": "generic_rest",
            "base_url": "https://agents.example.com",
            "collect_observability": True,
        },
    )
    assert conn.status_code == 201, conn.text
    assert conn.json()["collect_observability"] is True

    overview = await client.get("/api/v1/mission/overview")
    assert overview.status_code == 200, overview.text
    data = overview.json()
    assert "active_users_30d" in data
    assert "agent_runtime_hours_30d" in data
    assert "registry_sync" in data
    assert data["registry_sync"]["connected_platforms"] >= 1
    assert data["registry_sync"]["collect_observability_enabled"] >= 1
    assert data["total_agents"] >= 1


@pytest.mark.asyncio
async def test_collect_observability_toggle_and_pull(client: AsyncClient):
    conn = await client.post(
        "/api/v1/connectors",
        json={
            "name": "Obs Platform",
            "connector_type": "generic_rest",
            "base_url": "https://obs.example.com",
            "collect_observability": True,
        },
    )
    assert conn.status_code == 201, conn.text
    connection_id = conn.json()["id"]

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "fed-agent",
            "platform": "generic_rest",
            "framework": "generic_rest",
            "external_id": "ext-obs-1",
            "connection_id": connection_id,
            "lifecycle_state": "registered",
        },
    )
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    with patch(
        "app.services.activity.get_connector",
    ) as mock_get:
        fake = AsyncMock()
        fake.get_telemetry = AsyncMock(
            return_value={
                "sessions": 12,
                "exceptions": 1,
                "runtime_seconds": 3600,
                "unique_users": 4,
                "tool_calls": 7,
                "invocations": 12,
            }
        )
        mock_get.return_value = fake

        collect = await client.post(
            f"/api/v1/connectors/{connection_id}/collect-observability"
        )
    assert collect.status_code == 200, collect.text
    assert collect.json()["snapshots_upserted"] >= 1
    assert collect.json()["status"] in {"completed", "partial"}

    act = await client.get(f"/api/v1/agents/{agent_id}/activity")
    assert act.status_code == 200
    summary = act.json()
    assert summary["sessions"] >= 12
    assert "generic_rest" in summary["by_source"]

    # Disable collect
    patched = await client.patch(
        f"/api/v1/connectors/{connection_id}",
        json={"collect_observability": False},
    )
    assert patched.status_code == 200
    assert patched.json()["collect_observability"] is False

    skipped = await client.post(
        f"/api/v1/connectors/{connection_id}/collect-observability"
    )
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_otel_ingest_and_export(client: AsyncClient):
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "gen_ai.agent.id",
                            "value": {"stringValue": "otel-ext-99"},
                        },
                        {
                            "key": "gen_ai.agent.name",
                            "value": {"stringValue": "otel-demo"},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "invoke_agent",
                                "traceId": "abc123",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "1500000000",
                                "attributes": [
                                    {
                                        "key": "gen_ai.operation.name",
                                        "value": {"stringValue": "invoke_agent"},
                                    }
                                ],
                                "status": {"code": "OK"},
                            },
                            {
                                "name": "tool.search",
                                "traceId": "abc123",
                                "startTimeUnixNano": "1100000000",
                                "endTimeUnixNano": "1200000000",
                                "status": {"code": "OK"},
                            },
                        ]
                    }
                ],
            }
        ]
    }
    resp = await client.post("/api/v1/otel/v1/traces", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted_spans"] == 2
    assert body["executions_created"] == 1
    assert body["agent_id"]
    agent_id = body["agent_id"]

    export = await client.get(f"/api/v1/otel/agents/{agent_id}/export")
    assert export.status_code == 200, export.text
    exported = export.json()
    assert "resourceSpans" in exported
    spans = exported["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) >= 1

    act = await client.get(f"/api/v1/agents/{agent_id}/activity")
    assert act.status_code == 200
    assert act.json()["sessions"] >= 1 or act.json()["invocations"] >= 1


@pytest.mark.asyncio
async def test_otel_ingest_flat_spans(client: AsyncClient):
    resp = await client.post(
        "/api/v1/otel/v1/traces",
        json={
            "agent_external_id": f"flat-{uuid4().hex[:8]}",
            "spans": [
                {
                    "name": "invoke_agent",
                    "startTimeUnixNano": "1000",
                    "endTimeUnixNano": "2000000",
                    "status": {"code": "ERROR", "message": "boom"},
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["accepted_spans"] == 1


@pytest.mark.asyncio
async def test_activity_upsert_idempotent_day(session_factory, tenant_and_user):
    from app.models.agent import Agent
    from app.services import activity as activity_service

    tenant, _user = tenant_and_user
    async with session_factory() as db:
        agent = Agent(
            tenant_id=tenant.id,
            name="rollup-agent",
            platform="keel",
            framework="keel",
            lifecycle_state="registered",
        )
        db.add(agent)
        await db.flush()
        today = date.today()
        await activity_service._upsert_day(
            db,
            tenant_id=tenant.id,
            agent_id=agent.id,
            day=today,
            source="aws_bedrock",
            sessions=5,
            exceptions=0,
            runtime_seconds=100,
            unique_users=2,
            replace=True,
        )
        await activity_service._upsert_day(
            db,
            tenant_id=tenant.id,
            agent_id=agent.id,
            day=today,
            source="aws_bedrock",
            sessions=9,
            exceptions=1,
            runtime_seconds=200,
            unique_users=3,
            replace=True,
        )
        await db.commit()
        summary = await activity_service.agent_activity_summary(
            db, tenant_id=tenant.id, agent_id=agent.id, window_days=7
        )
        assert summary.by_source["aws_bedrock"]["sessions"] == 9
        assert summary.by_source["aws_bedrock"]["exceptions"] == 1
