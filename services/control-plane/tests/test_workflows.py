"""Workflow Orchestration — definitions, HITL pause/resume."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.connectors.base import InvokeResponse


@pytest.mark.asyncio
async def test_seed_and_list_definitions(client: AsyncClient):
    seeded = await client.post("/api/v1/workflows/seed")
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["created"] >= 1

    listed = await client.get("/api/v1/workflows/definitions")
    assert listed.status_code == 200
    defs = listed.json()
    assert len(defs) >= 3
    slugs = {d["slug"] for d in defs}
    assert "ad-delivery-pipeline" in slugs
    assert "ams-incident-to-change" in slugs
    assert any(d["hitl_count"] >= 1 for d in defs)


@pytest.mark.asyncio
async def test_qe_pipeline_hitl_resume(client: AsyncClient):
    await client.post("/api/v1/workflows/seed")
    defs = (await client.get("/api/v1/workflows/definitions?domain=QE")).json()
    qe = next(d for d in defs if d["slug"] == "qe-quality-gate")

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "qe-workflow-agent",
            "framework": "generic_rest",
            "domain": "QE",
            "lifecycle_state": "registered",
            "invoke_url": "http://127.0.0.1:9/invoke",
        },
    )
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    async def fake_invoke(request):  # noqa: ANN001
        return InvokeResponse(
            output={"cases": [{"id": "T1", "title": "refund", "priority": "P0"}], "scope": "refunds"},
            latency_ms=15.0,
            token_input=5,
            token_output=20,
            raw={},
        )

    with patch("app.services.execution.get_connector") as mock_get:
        connector = AsyncMock()
        connector.invoke_agent = AsyncMock(side_effect=fake_invoke)
        connector.connector_type = "generic_rest"
        mock_get.return_value = connector

        started = await client.post(
            "/api/v1/workflows/runs",
            json={
                "definition_id": qe["id"],
                "input": {"feature": "partial refund"},
                "agent_bindings": {"test_design": agent_id},
            },
        )
        assert started.status_code == 201, started.text
        run = started.json()
        assert run["status"] == "awaiting_approval", run
        assert run["pending_approval_id"], run
        assert run["steps"], run
        assert any(s["status"] == "succeeded" for s in run["steps"]), run["steps"]
        assert any(s["status"] == "awaiting_approval" for s in run["steps"]), run["steps"]

        approval_id = run["pending_approval_id"]
        decided = await client.post(
            f"/api/v1/approvals/{approval_id}/decide",
            json={"status": "approved", "decision_notes": "P0 looks good"},
        )
        assert decided.status_code == 200, decided.text

        final = await client.get(f"/api/v1/workflows/runs/{run['id']}")
        assert final.status_code == 200
        body = final.json()
        assert body["status"] == "succeeded"
        assert any(s["node_id"] == "triage_ready" and s["status"] == "succeeded" for s in body["steps"])


@pytest.mark.asyncio
async def test_hitl_reject_fails_run(client: AsyncClient):
    await client.post("/api/v1/workflows/seed")
    defs = (await client.get("/api/v1/workflows/definitions?domain=QE")).json()
    qe = next(d for d in defs if d["slug"] == "qe-quality-gate")

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "qe-reject-agent",
            "framework": "generic_rest",
            "domain": "QE",
            "lifecycle_state": "registered",
            "invoke_url": "http://127.0.0.1:9/invoke",
        },
    )
    agent_id = agent.json()["id"]

    async def fake_invoke(request):  # noqa: ANN001
        return InvokeResponse(output={"ok": True}, latency_ms=1.0, raw={})

    with patch("app.services.execution.get_connector") as mock_get:
        connector = AsyncMock()
        connector.invoke_agent = AsyncMock(side_effect=fake_invoke)
        connector.connector_type = "generic_rest"
        mock_get.return_value = connector

        started = await client.post(
            "/api/v1/workflows/runs",
            json={
                "definition_id": qe["id"],
                "input": {"feature": "x"},
                "agent_bindings": {"test_design": agent_id},
            },
        )
        run = started.json()
        rejected = await client.post(
            f"/api/v1/approvals/{run['pending_approval_id']}/decide",
            json={"status": "rejected", "decision_notes": "Coverage incomplete"},
        )
        assert rejected.status_code == 200
        final = (await client.get(f"/api/v1/workflows/runs/{run['id']}")).json()
        assert final["status"] == "failed"
