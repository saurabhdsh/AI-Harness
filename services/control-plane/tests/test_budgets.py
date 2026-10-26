"""FinOps budgets — Admin CRUD + period-aware spend."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.cost import CostRecord


@pytest.mark.asyncio
async def test_budget_crud(client: AsyncClient):
    created = await client.post(
        "/api/v1/costs/budgets",
        json={
            "name": "Monthly tenant cap",
            "scope": "tenant",
            "limit_usd": 10.0,
            "period": "monthly",
            "alert_threshold": 0.5,
        },
    )
    assert created.status_code == 201, created.text
    budget = created.json()
    assert budget["name"] == "Monthly tenant cap"
    assert budget["computed_spent_usd"] == 0.0
    assert budget["over_threshold"] is False
    budget_id = budget["id"]

    listed = await client.get("/api/v1/costs/budgets")
    assert listed.status_code == 200
    assert any(b["id"] == budget_id for b in listed.json())

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "cost-agent",
            "framework": "langgraph",
            "lifecycle_state": "registered",
            "invoke_url": "http://127.0.0.1:9/invoke",
        },
    )
    assert agent.status_code == 201
    agent_id = agent.json()["id"]

    patched = await client.patch(
        f"/api/v1/costs/budgets/{budget_id}",
        json={"limit_usd": 5.0, "alert_threshold": 0.8},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["limit_usd"] == 5.0

    bad = await client.post(
        "/api/v1/costs/budgets",
        json={"name": "Agent only", "scope": "agent", "limit_usd": 1.0},
    )
    assert bad.status_code == 422

    agent_budget = await client.post(
        "/api/v1/costs/budgets",
        json={
            "name": "Agent spend",
            "scope": "agent",
            "agent_id": agent_id,
            "limit_usd": 2.0,
            "period": "daily",
        },
    )
    assert agent_budget.status_code == 201, agent_budget.text
    assert agent_budget.json()["agent_id"] == agent_id

    deactivated = await client.delete(f"/api/v1/costs/budgets/{budget_id}")
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    summary = await client.get("/api/v1/costs/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert "rate_note" in body
    assert "budgets_over_threshold" in body


@pytest.mark.asyncio
async def test_budget_spend_reflects_cost_records(client: AsyncClient, session_factory):
    created = await client.post(
        "/api/v1/costs/budgets",
        json={
            "name": "Spend probe",
            "scope": "tenant",
            "limit_usd": 1.0,
            "period": "all_time",
            "alert_threshold": 0.1,
        },
    )
    assert created.status_code == 201, created.text
    budget = created.json()
    from uuid import UUID

    tenant_id = UUID(budget["tenant_id"])

    async with session_factory() as session:
        session.add(
            CostRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                cost_usd=0.25,
                token_input=100,
                token_output=50,
                model_name="test",
                metadata_={"source": "test"},
            )
        )
        await session.commit()

    refreshed = await client.get(f"/api/v1/costs/budgets/{budget['id']}")
    assert refreshed.status_code == 200, refreshed.text
    data = refreshed.json()
    assert data["computed_spent_usd"] >= 0.25
    assert data["pct_used"] >= 0.25
    assert data["over_threshold"] is True
