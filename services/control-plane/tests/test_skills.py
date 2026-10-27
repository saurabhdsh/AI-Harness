"""Skill Forge — catalog seed, attach, invoke injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.connectors.base import InvokeResponse


@pytest.mark.asyncio
async def test_skills_seed_and_list(client: AsyncClient):
    seeded = await client.post("/api/v1/skills/seed")
    assert seeded.status_code == 200, seeded.text
    body = seeded.json()
    assert body["created"] >= 1
    assert body["total"] >= body["created"]

    listed = await client.get("/api/v1/skills")
    assert listed.status_code == 200
    skills = listed.json()
    assert len(skills) >= 8
    slugs = {s["slug"] for s in skills}
    assert "ams-incident-rca" in slugs
    assert "qe-test-design" in slugs

    ad = await client.get("/api/v1/skills?domain=AD")
    assert ad.status_code == 200
    assert all(s["domain"] == "AD" for s in ad.json())

    # Idempotent re-seed
    again = await client.post("/api/v1/skills/seed")
    assert again.status_code == 200
    assert again.json()["created"] == 0


@pytest.mark.asyncio
async def test_attach_detach_and_invoke_injects_skills(client: AsyncClient):
    await client.post("/api/v1/skills/seed")
    skills = (await client.get("/api/v1/skills?domain=AMS")).json()
    skill = next(s for s in skills if s["slug"] == "ams-incident-rca")

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "ams-skill-agent",
            "framework": "generic_rest",
            "domain": "AMS",
            "lifecycle_state": "registered",
            "invoke_url": "http://127.0.0.1:9/invoke",
        },
    )
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    attached = await client.post(
        f"/api/v1/skills/by-agent/{agent_id}",
        json={"skill_id": skill["id"], "config": {"project": "checkout"}},
    )
    assert attached.status_code == 201, attached.text
    assert attached.json()["skill"]["slug"] == "ams-incident-rca"

    listed = await client.get(f"/api/v1/skills/by-agent/{agent_id}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    async def fake_invoke(request):  # noqa: ANN001
        return InvokeResponse(
            output={"summary": "ok", "root_cause": "cache", "harness_echo": request.input},
            latency_ms=12.0,
            token_input=10,
            token_output=20,
            raw={"config": request.config},
        )

    with patch("app.services.execution.get_connector") as mock_get:
        connector = AsyncMock()
        connector.invoke_agent = AsyncMock(side_effect=fake_invoke)
        connector.connector_type = "generic_rest"
        mock_get.return_value = connector

        inv = await client.post(
            f"/api/v1/agents/{agent_id}/invoke",
            json={
                "input": {"incident": "latency spike"},
                "config": {},
                "skill_slug": "ams-incident-rca",
            },
        )
        assert inv.status_code == 200, inv.text
        assert inv.json()["status"] == "succeeded"

        call = connector.invoke_agent.await_args
        req = call.args[0] if call.args else call.kwargs.get("request")
        assert "harness_skills" in req.input
        assert req.input["harness_skills"][0]["slug"] == "ams-incident-rca"
        assert "skills" in req.config
        assert "system_skills" in req.config
        assert "incident" in req.config["system_skills"].lower()

    detached = await client.delete(
        f"/api/v1/skills/by-agent/{agent_id}/{skill['id']}"
    )
    assert detached.status_code == 204
    after = await client.get(f"/api/v1/skills/by-agent/{agent_id}")
    assert after.json() == []


@pytest.mark.asyncio
async def test_custom_skill_create(client: AsyncClient):
    created = await client.post(
        "/api/v1/skills",
        json={
            "slug": "ad-custom-review",
            "name": "Custom Review",
            "domain": "AD",
            "instructions": "Review the change for style only.",
            "tags": ["custom"],
            "sample_input": {"diff": "..."},
        },
    )
    assert created.status_code == 201, created.text
    skill_id = created.json()["id"]
    assert created.json()["is_builtin"] is False

    patched = await client.patch(
        f"/api/v1/skills/{skill_id}",
        json={"description": "Style-focused review"},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Style-focused review"
