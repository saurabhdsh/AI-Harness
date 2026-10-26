"""Release Command — gated promotions across environments."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _register_agent(client: AsyncClient, name: str = "promo-agent", env: str = "dev") -> dict:
    resp = await client.post(
        "/api/v1/agents",
        json={
            "name": name,
            "platform": "local",
            "framework": "langgraph",
            "environment": env,
            "lifecycle_state": "registered",
            "risk_class": "medium",
            "evaluation_status": "none",
            "invoke_url": "http://127.0.0.1:8090/invoke",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_eval(client: AsyncClient, agent_id: str, status: str = "passed") -> None:
    resp = await client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"evaluation_status": status},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_release_board_and_default_train(client: AsyncClient):
    trains = await client.get("/api/v1/releases/trains")
    assert trains.status_code == 200
    data = trains.json()
    assert any(t["slug"] == "standard" for t in data)

    board = await client.get("/api/v1/releases/board")
    assert board.status_code == 200
    body = board.json()
    assert "environments" in body
    assert {e["environment"] for e in body["environments"]} >= {"dev", "staging", "prod"}


@pytest.mark.asyncio
async def test_promote_blocked_without_evaluation(client: AsyncClient):
    agent = await _register_agent(client, "needs-eval")
    resp = await client.post(
        "/api/v1/releases/promotions",
        json={
            "agent_id": agent["id"],
            "to_env": "staging",
            "justification": "try without eval",
        },
    )
    assert resp.status_code == 201, resp.text
    promo = resp.json()
    assert promo["status"] == "failed"
    assert promo["from_env"] == "dev"
    assert promo["to_env"] == "staging"
    assert any(g["type"] == "evaluation" and g["status"] == "failed" for g in promo["gates"])


@pytest.mark.asyncio
async def test_promote_staging_then_prod_with_approval(client: AsyncClient):
    agent = await _register_agent(client, "train-agent")
    await _set_eval(client, agent["id"], "passed")

    # staging: evaluation required, approval not required for medium risk
    staging = await client.post(
        "/api/v1/releases/promotions",
        json={"agent_id": agent["id"], "to_env": "staging", "justification": "to staging"},
    )
    assert staging.status_code == 201, staging.text
    promo = staging.json()
    assert promo["status"] == "completed"
    assert promo["to_env"] == "staging"

    agent2 = (await client.get(f"/api/v1/agents/{agent['id']}")).json()
    assert agent2["environment"] == "staging"
    assert agent2["lifecycle_state"] == "validated"

    # skip ahead to prod should fail (must be one stage)
    skip = await client.post(
        "/api/v1/releases/promotions",
        json={"agent_id": agent["id"], "to_env": "prod"},
    )
    # agent is staging → prod is allowed (one step). Wait - staging→prod is next. Good.
    # Actually from staging, next is prod. So skip to something else:
    bad = await client.post(
        "/api/v1/releases/promotions",
        json={"agent_id": agent["id"], "to_env": "dev"},
    )
    assert bad.status_code == 400

    prod = await client.post(
        "/api/v1/releases/promotions",
        json={"agent_id": agent["id"], "to_env": "prod", "justification": "go live"},
    )
    assert prod.status_code == 201, prod.text
    waiting = prod.json()
    assert waiting["status"] == "awaiting_approval"
    assert waiting["approval_id"]

    approved = await client.post(f"/api/v1/releases/promotions/{waiting['id']}/approve")
    assert approved.status_code == 200, approved.text
    done = approved.json()
    assert done["status"] == "completed"

    final = (await client.get(f"/api/v1/agents/{agent['id']}")).json()
    assert final["environment"] == "prod"
    assert final["lifecycle_state"] == "production"


@pytest.mark.asyncio
async def test_reject_promotion_via_governance(client: AsyncClient):
    agent = await _register_agent(client, "reject-me")
    await _set_eval(client, agent["id"], "passed")
    await client.post(
        "/api/v1/releases/promotions",
        json={"agent_id": agent["id"], "to_env": "staging"},
    )
    # move to staging first
    agent = (await client.get(f"/api/v1/agents/{agent['id']}")).json()
    assert agent["environment"] == "staging"

    prod = await client.post(
        "/api/v1/releases/promotions",
        json={"agent_id": agent["id"], "to_env": "prod"},
    )
    waiting = prod.json()
    assert waiting["status"] == "awaiting_approval"

    decide = await client.post(
        f"/api/v1/approvals/{waiting['approval_id']}/decide",
        json={"status": "rejected", "decision_notes": "not ready"},
    )
    assert decide.status_code == 200

    promo = (await client.get(f"/api/v1/releases/promotions/{waiting['id']}")).json()
    assert promo["status"] == "rejected"

    still = (await client.get(f"/api/v1/agents/{agent['id']}")).json()
    assert still["environment"] == "staging"
