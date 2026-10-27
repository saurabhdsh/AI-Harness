"""Seed demo tenant, admin user, and LangGraph example agent.

Usage:
  PYTHONPATH=. python -m app.seed
  # or
  PYTHONPATH=. python app/seed.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, init_db
from app.models.agent import Agent, AgentVersion
from app.models.connection import PlatformConnection
from app.models.tenant import Tenant
from app.models.user import User
from app.connectors.langgraph import LangGraphConnector


async def seed() -> None:
    settings = get_settings()
    await init_db()

    # Prefer docker service name; allow localhost override for host-run demos
    agent_url = os.getenv(
        "LANGGRAPH_AGENT_URL",
        settings.langgraph_agent_url,
    )
    if os.getenv("SEED_USE_LOCALHOST") == "1":
        agent_url = "http://localhost:8080"

    async with AsyncSessionLocal() as db:
        # Tenant
        result = await db.execute(select(Tenant).where(Tenant.slug == "demo"))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                name="Demo Tenant",
                slug="demo",
                description="Seeded demo tenant",
            )
            db.add(tenant)
            await db.flush()
            print(f"Created tenant {tenant.id}")
        else:
            print(f"Tenant exists {tenant.id}")

        # Admin user
        result = await db.execute(select(User).where(User.email == settings.demo_admin_email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=settings.demo_admin_email,
                hashed_password=hash_password(settings.demo_admin_password),
                full_name="Harness Admin",
                role="admin",
                is_active=True,
            )
            db.add(user)
            await db.flush()
            print(f"Created admin {user.email}")
        else:
            print(f"Admin exists {user.email}")

        # Platform connection
        result = await db.execute(
            select(PlatformConnection).where(
                PlatformConnection.tenant_id == tenant.id,
                PlatformConnection.name == "langgraph-demo",
            )
        )
        conn = result.scalar_one_or_none()
        if conn is None:
            connector = LangGraphConnector(base_url=agent_url)
            caps = await connector.get_capabilities()
            conn = PlatformConnection(
                tenant_id=tenant.id,
                name="langgraph-demo",
                connector_type="langgraph",
                base_url=agent_url.rstrip("/"),
                secret_ref="vault:demo/langgraph",
                capabilities=caps.model_dump(),
                status="seeded",
                metadata_={"seeded": True},
            )
            db.add(conn)
            await db.flush()
            print(f"Created connection {conn.id} -> {agent_url}")
        else:
            print(f"Connection exists {conn.id}")

        # LangGraph agent
        result = await db.execute(
            select(Agent).where(
                Agent.tenant_id == tenant.id,
                Agent.external_id == "ad-code-engineering",
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            invoke_url = f"{agent_url.rstrip('/')}/invoke"
            agent = Agent(
                tenant_id=tenant.id,
                name="AD Code Engineering Agent",
                platform="langgraph",
                framework="langgraph",
                external_id="ad-code-engineering",
                owner="demo",
                team="ad-engineering",
                domain="ad",
                environment="dev",
                lifecycle_state="registered",
                risk_class="low",
                health_status="unknown",
                evaluation_status="none",
                connection_id=conn.id,
                invoke_url=invoke_url,
                description="Externally developed LangGraph-style AD code agent (onboarded without rewrite)",
                metadata_={"seeded": True, "category": "code_engineering"},
            )
            db.add(agent)
            await db.flush()
            db.add(
                AgentVersion(
                    tenant_id=tenant.id,
                    agent_id=agent.id,
                    version="0.1.0",
                    changelog="Seed registration",
                    config={},
                    is_active=True,
                )
            )
            print(f"Registered agent {agent.id} invoke={invoke_url}")
        else:
            print(f"Agent exists {agent.id}")

        from app.skills.service import ensure_builtin_skills

        n = await ensure_builtin_skills(db, tenant.id)
        print(f"Skill Forge built-ins: +{n}")

        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
