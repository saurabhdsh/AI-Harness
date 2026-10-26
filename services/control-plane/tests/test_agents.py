"""Tests: register agent, invoke with httpx mock, unsupported deploy, evaluation, cross-tenant."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.connectors.base import UnsupportedOperationError
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import create_app


def _mock_httpx_client(response: httpx.Response):
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            return response

        async def get(self, url, **kwargs):
            return httpx.Response(200, json={"status": "ok"})

    return _Client


@pytest.mark.asyncio
async def test_register_agent(client: AsyncClient):
    resp = await client.post(
        "/api/v1/agents",
        json={
            "name": "demo-agent",
            "platform": "langgraph",
            "framework": "langgraph",
            "invoke_url": "http://langgraph-agent:8080/invoke",
            "lifecycle_state": "registered",
            "owner": "qa",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "demo-agent"
    assert data["lifecycle_state"] == "registered"
    assert data["tenant_id"] == str(client.tenant_id)

    listed = await client.get("/api/v1/agents")
    assert listed.status_code == 200
    assert any(a["id"] == data["id"] for a in listed.json())


@pytest.mark.asyncio
async def test_invoke_agent_with_httpx_mock(client: AsyncClient):
    create = await client.post(
        "/api/v1/agents",
        json={
            "name": "invoke-me",
            "framework": "langgraph",
            "invoke_url": "http://fake-agent:8080/invoke",
            "lifecycle_state": "registered",
        },
    )
    assert create.status_code == 201
    agent_id = create.json()["id"]

    mock_response = httpx.Response(
        200,
        json={
            "output": {"message": "pong"},
            "usage": {"input_tokens": 3, "output_tokens": 1},
            "run_id": "trace-abc",
        },
    )

    with patch("httpx.AsyncClient", _mock_httpx_client(mock_response)):
        resp = await client.post(
            f"/api/v1/agents/{agent_id}/invoke",
            json={"input": {"message": "ping"}},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["output"]["message"] == "pong"
    assert body["token_input"] == 3
    assert body["execution_id"]


@pytest.mark.asyncio
async def test_unsupported_deploy_returns_typed_error(client: AsyncClient):
    conn = await client.post(
        "/api/v1/connectors",
        json={
            "name": "lg",
            "connector_type": "langgraph",
            "base_url": "http://langgraph-agent:8080",
            "secret_ref": "vault:demo/key",
        },
    )
    assert conn.status_code == 201, conn.text
    connection_id = conn.json()["id"]

    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "no-deploy",
            "framework": "langgraph",
            "connection_id": connection_id,
            "invoke_url": "http://langgraph-agent:8080/invoke",
        },
    )
    assert agent.status_code == 201
    agent_id = agent.json()["id"]

    resp = await client.post(f"/api/v1/agents/{agent_id}/deploy")
    assert resp.status_code == 501
    detail = resp.json()["detail"]
    if isinstance(detail, dict):
        assert detail["error_type"] == "UnsupportedOperationError"
        assert detail["operation"] == "deploy"
        assert detail["connector_type"] == "langgraph"
    else:
        assert "deploy" in str(detail).lower()


@pytest.mark.asyncio
async def test_evaluation_run(client: AsyncClient):
    create = await client.post(
        "/api/v1/agents",
        json={
            "name": "eval-agent",
            "framework": "generic_rest",
            "invoke_url": "http://fake-agent:8080/invoke",
        },
    )
    agent_id = create.json()["id"]

    mock_response = httpx.Response(
        200,
        json={"output": {"answer": "42", "ok": True}},
    )

    with patch("httpx.AsyncClient", _mock_httpx_client(mock_response)):
        resp = await client.post(
            "/api/v1/evaluations",
            json={
                "agent_id": agent_id,
                "name": "unit-suite",
                "use_llm_judge": False,
                "cases": [
                    {
                        "case_id": "c1",
                        "input": {"q": "life"},
                        "expected": {"answer": "42"},
                        "match_mode": "contains",
                    }
                ],
            },
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "completed"
    assert data["aggregate_score"] is not None
    assert data["aggregate_score"] >= 0.7
    assert len(data["results"]) == 1
    assert data["results"][0]["passed"] is True


@pytest.mark.asyncio
async def test_cross_tenant_denial(client: AsyncClient, other_tenant_user, session_factory):
    create = await client.post(
        "/api/v1/agents",
        json={"name": "tenant-a-agent", "framework": "rest", "invoke_url": "http://x/invoke"},
    )
    assert create.status_code == 201
    agent_id = create.json()["id"]

    other_tenant, other_user = other_tenant_user
    other_token = create_access_token(
        subject=other_user.email,
        tenant_id=other_tenant.id,
        user_id=other_user.id,
    )

    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    @asynccontextmanager
    async def _noop(app):
        yield

    app.router.lifespan_context = _noop

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        other.headers["Authorization"] = f"Bearer {other_token}"
        get_resp = await other.get(f"/api/v1/agents/{agent_id}")
        assert get_resp.status_code == 404

        invoke_resp = await other.post(
            f"/api/v1/agents/{agent_id}/invoke",
            json={"input": {"x": 1}},
        )
        assert invoke_resp.status_code == 404


@pytest.mark.asyncio
async def test_langgraph_connector_unsupported_deploy_direct():
    from app.connectors.langgraph import LangGraphConnector

    c = LangGraphConnector(base_url="http://example.com")
    with pytest.raises(UnsupportedOperationError) as ei:
        await c.deploy({"x": 1})
    assert ei.value.operation == "deploy"
    assert ei.value.connector_type == "langgraph"
