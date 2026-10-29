"""Agent 365–style registry: blueprints, unique external_id, connection sync."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_blueprint_crud_and_register(client: AsyncClient):
    created = await client.post(
        "/api/v1/blueprints",
        json={
            "name": "AD Story Blueprint",
            "slug": "ad-story",
            "description": "Reusable AD agent template",
            "connector_type": "generic_rest",
            "framework": "langgraph",
            "default_domain": "AD",
            "default_risk_class": "high",
            "permissions": {"invoke": True},
        },
    )
    assert created.status_code == 201, created.text
    bp = created.json()
    assert bp["slug"] == "ad-story"
    bp_id = bp["id"]

    dup = await client.post(
        "/api/v1/blueprints",
        json={
            "name": "Dup",
            "slug": "ad-story",
            "connector_type": "generic_rest",
        },
    )
    assert dup.status_code == 409

    listed = await client.get("/api/v1/blueprints")
    assert listed.status_code == 200
    assert any(x["id"] == bp_id for x in listed.json())

    reg = await client.post(
        f"/api/v1/blueprints/{bp_id}/register",
        json={
            "name": "AD Story Instance",
            "external_id": "ad-story-prod-1",
            "invoke_url": "http://127.0.0.1:8091/agents/ad-story/invoke",
            "environment": "prod",
        },
    )
    assert reg.status_code == 201, reg.text
    agent = reg.json()
    assert agent["external_id"] == "ad-story-prod-1"
    assert agent["blueprint_id"] == bp_id
    assert agent["lifecycle_state"] == "registered"
    assert agent["domain"] == "AD"
    assert agent["risk_class"] == "high"
    assert agent["metadata"]["blueprint_slug"] == "ad-story"

    # Idempotent upsert via same blueprint
    again = await client.post(
        f"/api/v1/blueprints/{bp_id}/register",
        json={
            "name": "AD Story Instance v2",
            "external_id": "ad-story-prod-1",
            "invoke_url": "http://127.0.0.1:8091/agents/ad-story/invoke",
        },
    )
    assert again.status_code == 201
    assert again.json()["id"] == agent["id"]
    assert again.json()["name"] == "AD Story Instance v2"


@pytest.mark.asyncio
async def test_ci_register_with_blueprint_slug(client: AsyncClient):
    bp = await client.post(
        "/api/v1/blueprints",
        json={
            "name": "CI Blueprint",
            "slug": "ci-bp",
            "connector_type": "generic_rest",
            "framework": "rest",
            "default_domain": "QE",
        },
    )
    assert bp.status_code == 201, bp.text

    res = await client.post(
        "/api/v1/onboarding/ci/register",
        json={
            "name": "QE from blueprint",
            "external_id": "qe-from-bp",
            "invoke_url": "http://127.0.0.1:8091/agents/qe/invoke",
            "blueprint_slug": "ci-bp",
            "git_repo": "https://github.com/acme/qe",
            "git_sha": "abc123",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["created"] is True
    assert body["blueprint_id"] == bp.json()["id"]

    agent = await client.get(f"/api/v1/agents/{body['agent_id']}")
    assert agent.status_code == 200
    data = agent.json()
    assert data["domain"] == "QE"
    assert data["blueprint_id"] == bp.json()["id"]
    assert data["metadata"]["blueprint_slug"] == "ci-bp"


@pytest.mark.asyncio
async def test_unique_external_id_upsert_no_duplicates(client: AsyncClient):
    a = await client.post(
        "/api/v1/onboarding/ci/register",
        json={
            "name": "Unique A",
            "external_id": "unique-ext-1",
            "invoke_url": "http://127.0.0.1:1/invoke",
        },
    )
    b = await client.post(
        "/api/v1/onboarding/ci/register",
        json={
            "name": "Unique B",
            "external_id": "unique-ext-1",
            "invoke_url": "http://127.0.0.1:1/invoke-v2",
        },
    )
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["agent_id"] == b.json()["agent_id"]
    assert b.json()["created"] is False

    agents = await client.get("/api/v1/agents?limit=200")
    matches = [x for x in agents.json() if x.get("external_id") == "unique-ext-1"]
    assert len(matches) == 1
    assert matches[0]["invoke_url"] == "http://127.0.0.1:1/invoke-v2"


@pytest.mark.asyncio
async def test_connection_sync_into_registry(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    from app.connectors.base import CapabilityManifest, DiscoveredAgent
    from app.services import onboarding as onboarding_service

    class _FakeConnector:
        connector_type = "generic_rest"

        async def authenticate(self) -> bool:
            return True

        async def get_capabilities(self) -> CapabilityManifest:
            return CapabilityManifest(discovery=True, metadata=True, invocation=True)

        async def discover_agents(self) -> list[DiscoveredAgent]:
            return [
                DiscoveredAgent(
                    external_id="synced-alpha",
                    name="Synced Alpha",
                    framework="rest",
                    invoke_url="http://platform.example/agents/synced-alpha/invoke",
                ),
                DiscoveredAgent(
                    external_id="synced-beta",
                    name="Synced Beta",
                    framework="rest",
                    invoke_url="http://platform.example/agents/synced-beta/invoke",
                ),
            ]

    monkeypatch.setattr(
        onboarding_service,
        "get_connector",
        lambda *args, **kwargs: _FakeConnector(),
    )

    conn = await client.post(
        "/api/v1/connectors",
        json={
            "name": "sync-platform",
            "connector_type": "generic_rest",
            "base_url": "http://platform.example",
            "metadata": {"source": "test"},
        },
    )
    assert conn.status_code == 201, conn.text
    cid = conn.json()["id"]

    sync = await client.post(f"/api/v1/connectors/{cid}/sync")
    assert sync.status_code == 200, sync.text
    body = sync.json()
    assert body["status"] == "completed", body
    assert body["connection_id"] == cid
    assert len(body["registered_agent_ids"]) == 2

    refreshed = await client.get(f"/api/v1/connectors/{cid}")
    assert refreshed.status_code == 200
    c = refreshed.json()
    assert c["last_sync_status"] == "completed"
    assert c["synced_agent_count"] == 2
    assert c["last_synced_at"] is not None

    # Second sync updates rather than duplicating by external_id
    again = await client.post(f"/api/v1/connectors/{cid}/sync")
    assert again.status_code == 200
    assert again.json()["status"] == "completed"
    assert len(again.json()["updated_agent_ids"]) == 2
    assert again.json()["registered_agent_ids"] == []
