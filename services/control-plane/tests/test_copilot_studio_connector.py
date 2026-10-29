"""Copilot Studio connector — registry listing + capability-honest auth."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.connectors.copilot_studio import CopilotStudioConnector
from app.connectors.registry import get_connector, list_connector_types


def test_copilot_studio_in_registry():
    ids = {c["id"] for c in list_connector_types()}
    assert "copilot_studio" in ids
    conn = get_connector(
        "copilot_studio",
        base_url="https://org.crm.dynamics.com",
        secret_ref="bearer:test-token",
    )
    assert isinstance(conn, CopilotStudioConnector)
    assert conn.connector_type == "copilot_studio"


@pytest.mark.asyncio
async def test_copilot_studio_requires_credentials():
    conn = CopilotStudioConnector(base_url="https://org.crm.dynamics.com", secret_ref=None)
    with pytest.raises(PermissionError):
        await conn.authenticate()


@pytest.mark.asyncio
async def test_frameworks_lists_copilot_studio(client: AsyncClient):
    res = await client.get("/api/v1/onboarding/frameworks")
    assert res.status_code == 200
    ids = {c["id"] for c in res.json().get("connectors", [])}
    assert "copilot_studio" in ids
