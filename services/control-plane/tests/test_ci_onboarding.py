"""CI / catalog enterprise onboarding."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ci_register_upsert(client: AsyncClient):
    first = await client.post(
        "/api/v1/onboarding/ci/register",
        json={
            "name": "CI Agent",
            "external_id": "ci-agent-1",
            "invoke_url": "http://127.0.0.1:8099/agents/ci-agent-1/invoke",
            "connector_type": "generic_rest",
            "domain": "AD",
            "environment": "staging",
            "git_repo": "https://github.com/acme/agents",
            "git_ref": "main",
            "git_sha": "deadbeef",
            "pipeline_id": "42",
        },
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["created"] is True
    assert body["external_id"] == "ci-agent-1"
    agent_id = body["agent_id"]

    second = await client.post(
        "/api/v1/onboarding/ci/register",
        json={
            "name": "CI Agent v2",
            "external_id": "ci-agent-1",
            "invoke_url": "http://127.0.0.1:8099/agents/ci-agent-1/invoke",
            "git_sha": "cafebabe",
            "environment": "prod",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["created"] is False
    assert second.json()["agent_id"] == agent_id

    agent = await client.get(f"/api/v1/agents/{agent_id}")
    assert agent.status_code == 200
    data = agent.json()
    assert data["name"] == "CI Agent v2"
    assert data["environment"] == "prod"
    assert data["metadata"]["git_sha"] == "cafebabe"
    assert data["metadata"]["source"] == "ci"


@pytest.mark.asyncio
async def test_catalog_sync_explicit_agents(client: AsyncClient):
    res = await client.post(
        "/api/v1/onboarding/catalog/sync",
        json={
            "name": "test-catalog",
            "connector_type": "generic_rest",
            "base_url": "http://127.0.0.1:9",
            "discover": False,
            "git_repo": "https://github.com/acme/fleet",
            "agents": [
                {
                    "name": "Alpha",
                    "external_id": "alpha",
                    "invoke_url": "http://127.0.0.1:9/agents/alpha/invoke",
                    "domain": "AD",
                },
                {
                    "name": "Beta",
                    "external_id": "beta",
                    "invoke_url": "http://127.0.0.1:9/agents/beta/invoke",
                    "domain": "AMS",
                },
            ],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "completed"
    assert len(body["registered_agent_ids"]) == 2

    # Re-sync updates rather than duplicating
    again = await client.post(
        "/api/v1/onboarding/catalog/sync",
        json={
            "name": "test-catalog-2",
            "connector_type": "generic_rest",
            "base_url": "http://127.0.0.1:9",
            "discover": False,
            "agents": [
                {
                    "name": "Alpha Updated",
                    "external_id": "alpha",
                    "invoke_url": "http://127.0.0.1:9/agents/alpha/invoke",
                }
            ],
        },
    )
    assert again.status_code == 201, again.text
    assert len(again.json()["updated_agent_ids"]) == 1
    assert again.json()["registered_agent_ids"] == []
