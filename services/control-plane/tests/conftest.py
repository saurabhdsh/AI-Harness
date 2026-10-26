"""Pytest fixtures — shared in-memory SQLite + FastAPI AsyncClient."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.tenant import Tenant
from app.models.user import User

import app.models  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@asynccontextmanager
async def _noop_lifespan(app):
    yield


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def tenant_and_user(session_factory):
    async with session_factory() as session:
        tenant = Tenant(name="Test Tenant", slug=f"test-{uuid.uuid4().hex[:8]}")
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant.id,
            email=f"admin-{uuid.uuid4().hex[:8]}@harness.local",
            hashed_password=hash_password("harness-admin"),
            full_name="Test Admin",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(tenant)
        await session.refresh(user)
        return tenant, user


@pytest_asyncio.fixture
async def other_tenant_user(session_factory):
    async with session_factory() as session:
        tenant = Tenant(name="Other Tenant", slug=f"other-{uuid.uuid4().hex[:8]}")
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant.id,
            email=f"other-{uuid.uuid4().hex[:8]}@harness.local",
            hashed_password=hash_password("other-pass"),
            full_name="Other Admin",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(tenant)
        await session.refresh(user)
        return tenant, user


@pytest_asyncio.fixture
async def client(session_factory, tenant_and_user) -> AsyncGenerator[AsyncClient, None]:
    tenant, user = tenant_and_user
    app = create_app()
    app.router.lifespan_context = _noop_lifespan

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token(
        subject=user.email,
        tenant_id=tenant.id,
        user_id=user.id,
        extra={"role": user.role},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        ac.tenant_id = tenant.id  # type: ignore[attr-defined]
        ac.user_id = user.id  # type: ignore[attr-defined]
        ac.user_email = user.email  # type: ignore[attr-defined]
        yield ac

    app.dependency_overrides.clear()
