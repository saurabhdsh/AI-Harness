"""Source-platform lifecycle controls (beyond Agent 365 read-only)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient


class _FakeLifecycleConnector:
    connector_type = "aws_bedrock"

    def __init__(self, *args: Any, **kwargs: Any):
        self.calls: list[tuple] = []

    async def authenticate(self) -> bool:
        return True

    async def get_capabilities(self):
        from app.connectors.base import CapabilityManifest

        return CapabilityManifest(
            discovery=True,
            suspension=True,
            resume=True,
            restart=True,
            deployment=True,
            rollback=True,
            delete_source=True,
        )

    async def suspend(self, external_id: str) -> dict:
        self.calls.append(("suspend", external_id))
        return {"operation": "suspend", "agent_id": external_id, "snapshot": {"v": "1"}}

    async def resume(self, external_id: str) -> dict:
        self.calls.append(("resume", external_id))
        return {"operation": "resume", "agent_id": external_id}

    async def restart(self, external_id: str) -> dict:
        self.calls.append(("restart", external_id))
        return {"operation": "restart", "agent_id": external_id}

    async def deploy(self, payload: dict) -> dict:
        self.calls.append(("deploy", payload))
        return {"operation": "deploy", "version": "3", **payload}

    async def rollback(self, external_id: str, version: str) -> dict:
        self.calls.append(("rollback", external_id, version))
        return {"operation": "rollback", "version": version}

    async def delete_from_source(self, external_id: str) -> dict:
        self.calls.append(("delete_from_source", external_id))
        return {"operation": "delete_from_source", "deleted": True}


@pytest.fixture
def fake_connector(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeLifecycleConnector()
    from app.services import lifecycle as lifecycle_svc

    monkeypatch.setattr(
        lifecycle_svc,
        "get_connector",
        lambda *a, **k: fake,
    )
    return fake


@pytest.mark.asyncio
async def test_lifecycle_stop_start_restart(client: AsyncClient, fake_connector):
    created = await client.post(
        "/api/v1/agents",
        json={
            "name": "Bedrock Bot",
            "platform": "aws_bedrock",
            "framework": "bedrock",
            "external_id": "AGENT123",
            "lifecycle_state": "registered",
        },
    )
    assert created.status_code == 201, created.text
    agent_id = created.json()["id"]

    stop = await client.post(f"/api/v1/agents/{agent_id}/stop", json={})
    assert stop.status_code == 200, stop.text
    assert stop.json()["operation"] == "suspend"
    assert stop.json()["status"] == "completed"

    agent = await client.get(f"/api/v1/agents/{agent_id}")
    assert agent.json()["lifecycle_state"] == "suspended"

    start = await client.post(f"/api/v1/agents/{agent_id}/start", json={})
    assert start.status_code == 200
    assert start.json()["operation"] == "resume"

    restart = await client.post(f"/api/v1/agents/{agent_id}/restart", json={})
    assert restart.status_code == 200
    assert restart.json()["operation"] == "restart"

    assert ("suspend", "AGENT123") in fake_connector.calls
    assert ("resume", "AGENT123") in fake_connector.calls
    assert ("restart", "AGENT123") in fake_connector.calls


@pytest.mark.asyncio
async def test_lifecycle_deploy_rollback(client: AsyncClient, fake_connector):
    created = await client.post(
        "/api/v1/agents",
        json={
            "name": "Bedrock Deploy",
            "platform": "aws_bedrock",
            "external_id": "DEP1",
            "lifecycle_state": "registered",
        },
    )
    agent_id = created.json()["id"]

    deploy = await client.post(f"/api/v1/agents/{agent_id}/deploy", json={})
    assert deploy.status_code == 200, deploy.text
    assert deploy.json()["operation"] == "deploy"

    rb = await client.post(
        f"/api/v1/agents/{agent_id}/rollback",
        json={"version": "2"},
    )
    assert rb.status_code == 200, rb.text
    assert rb.json()["detail"]["version"] == "2"


@pytest.mark.asyncio
async def test_delete_source_creates_approval(client: AsyncClient, fake_connector):
    created = await client.post(
        "/api/v1/agents",
        json={
            "name": "To Delete",
            "platform": "aws_bedrock",
            "external_id": "DEL1",
        },
    )
    agent_id = created.json()["id"]

    res = await client.post(
        f"/api/v1/agents/{agent_id}/delete-source",
        json={"confirm_delete_source": True, "create_approval": True},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "awaiting_approval"
    assert body["approval_id"]
    assert not any(c[0] == "delete_from_source" for c in fake_connector.calls)

    # Approve → executes delete
    decide = await client.post(
        f"/api/v1/approvals/{body['approval_id']}/decide",
        json={"status": "approved", "decision_notes": "ok"},
    )
    assert decide.status_code == 200, decide.text
    assert any(c[0] == "delete_from_source" for c in fake_connector.calls)

    agent = await client.get(f"/api/v1/agents/{agent_id}")
    assert agent.json()["lifecycle_state"] == "retired"


@pytest.mark.asyncio
async def test_bedrock_capabilities_advertise_writes():
    from app.connectors.aws_bedrock import AWSBedrockConnector

    caps = await AWSBedrockConnector(secret_ref="x").get_capabilities()
    assert caps.deployment is True
    assert caps.rollback is True
    assert caps.suspension is True
    assert caps.resume is True
    assert caps.restart is True
    assert caps.delete_source is True


@pytest.mark.asyncio
async def test_copilot_capabilities_advertise_writes():
    from app.connectors.copilot_studio import CopilotStudioConnector

    caps = await CopilotStudioConnector(
        base_url="https://org.crm.dynamics.com", secret_ref="bearer:x"
    ).get_capabilities()
    assert caps.suspension is True
    assert caps.resume is True
    assert caps.restart is True
    assert caps.deployment is True
    assert caps.delete_source is True
    assert caps.rollback is False
