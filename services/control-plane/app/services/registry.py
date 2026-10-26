"""Agent registry service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentVersion
from app.models.connection import PlatformConnection
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services.audit import record_audit


async def create_agent(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    data: AgentCreate,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> Agent:
    if data.connection_id:
        conn = await db.get(PlatformConnection, data.connection_id)
        if conn is None or conn.tenant_id != tenant_id:
            raise LookupError("Connection not found for tenant")

    agent = Agent(
        tenant_id=tenant_id,
        name=data.name,
        platform=data.platform,
        framework=data.framework,
        external_id=data.external_id,
        owner=data.owner,
        team=data.team,
        domain=data.domain,
        environment=data.environment,
        lifecycle_state=data.lifecycle_state,
        risk_class=data.risk_class,
        connection_id=data.connection_id,
        invoke_url=data.invoke_url,
        description=data.description,
        metadata_=data.metadata,
        health_status="unknown",
        evaluation_status="none",
    )
    db.add(agent)
    await db.flush()

    version = AgentVersion(
        tenant_id=tenant_id,
        agent_id=agent.id,
        version="0.1.0",
        changelog="Initial registration",
        config={},
        is_active=True,
    )
    db.add(version)
    await db.flush()

    await record_audit(
        db,
        tenant_id=tenant_id,
        action="agent.registered",
        resource_type="agent",
        resource_id=str(agent.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"name": agent.name, "framework": agent.framework},
    )
    return agent


async def list_agents(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[Agent]:
    stmt = (
        select(Agent)
        .where(Agent.tenant_id == tenant_id)
        .order_by(Agent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, *, tenant_id: UUID, agent_id: UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != tenant_id:
        raise LookupError("Agent not found")
    return agent


async def update_agent(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    data: AgentUpdate,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> Agent:
    agent = await get_agent(db, tenant_id=tenant_id, agent_id=agent_id)
    updates = data.model_dump(exclude_unset=True)
    if "metadata" in updates:
        agent.metadata_ = updates.pop("metadata") or {}
    for key, value in updates.items():
        setattr(agent, key, value)
    await db.flush()
    await record_audit(
        db,
        tenant_id=tenant_id,
        action="agent.updated",
        resource_type="agent",
        resource_id=str(agent.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail=updates,
    )
    return agent


async def delete_agent(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> None:
    agent = await get_agent(db, tenant_id=tenant_id, agent_id=agent_id)
    await record_audit(
        db,
        tenant_id=tenant_id,
        action="agent.deleted",
        resource_type="agent",
        resource_id=str(agent.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"name": agent.name},
    )
    await db.delete(agent)
    await db.flush()


def agent_to_dict(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "tenant_id": agent.tenant_id,
        "name": agent.name,
        "platform": agent.platform,
        "framework": agent.framework,
        "external_id": agent.external_id,
        "owner": agent.owner,
        "team": agent.team,
        "domain": agent.domain,
        "environment": agent.environment,
        "lifecycle_state": agent.lifecycle_state,
        "risk_class": agent.risk_class,
        "health_status": agent.health_status,
        "evaluation_status": agent.evaluation_status,
        "connection_id": agent.connection_id,
        "invoke_url": agent.invoke_url,
        "description": agent.description,
        "metadata_": agent.metadata_,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }
