"""Health endpoint (unauthenticated)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from contextlib import asynccontextmanager


@asynccontextmanager
async def _noop(app):
    yield


@pytest.mark.asyncio
async def test_health():
    app = create_app()
    app.router.lifespan_context = _noop
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
