"""Agent identity blueprints — reusable templates for registry registrations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blueprint import AgentBlueprint
from app.schemas.agent import AgentCreate
from app.schemas.blueprint import BlueprintCreate, BlueprintRegisterRequest, BlueprintUpdate
from app.services import registry as agent_registry
from app.services.audit import record_audit


async def list_blueprints(db: AsyncSession, *, tenant_id: UUID) -> list[AgentBlueprint]:
    result = await db.execute(
        select(AgentBlueprint)
        .where(AgentBlueprint.tenant_id == tenant_id)
        .order_by(AgentBlueprint.name)
    )
    return list(result.scalars().all())


async def get_blueprint(
    db: AsyncSession, *, tenant_id: UUID, blueprint_id: UUID
) -> AgentBlueprint:
    bp = await db.get(AgentBlueprint, blueprint_id)
    if bp is None or bp.tenant_id != tenant_id:
        raise LookupError("Blueprint not found")
    return bp


async def find_blueprint_by_slug(
    db: AsyncSession, *, tenant_id: UUID, slug: str
) -> AgentBlueprint | None:
    if not slug:
        return None
    result = await db.execute(
        select(AgentBlueprint).where(
            AgentBlueprint.tenant_id == tenant_id,
            AgentBlueprint.slug == slug,
        )
    )
    return result.scalar_one_or_none()


async def resolve_blueprint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    blueprint_id: UUID | None = None,
    blueprint_slug: str | None = None,
) -> AgentBlueprint | None:
    if blueprint_id:
        return await get_blueprint(db, tenant_id=tenant_id, blueprint_id=blueprint_id)
    if blueprint_slug:
        bp = await find_blueprint_by_slug(db, tenant_id=tenant_id, slug=blueprint_slug)
        if bp is None:
            raise LookupError(f"Blueprint slug not found: {blueprint_slug}")
        return bp
    return None


async def create_blueprint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    data: BlueprintCreate,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> AgentBlueprint:
    existing = await find_blueprint_by_slug(db, tenant_id=tenant_id, slug=data.slug)
    if existing:
        raise ValueError(f"Blueprint slug already exists: {data.slug}")

    bp = AgentBlueprint(
        tenant_id=tenant_id,
        name=data.name,
        slug=data.slug,
        description=data.description,
        connector_type=data.connector_type,
        framework=data.framework,
        default_domain=data.default_domain,
        default_risk_class=data.default_risk_class,
        permissions=data.permissions or {},
        metadata_=data.metadata or {},
    )
    db.add(bp)
    await db.flush()
    await record_audit(
        db,
        tenant_id=tenant_id,
        action="blueprint.created",
        resource_type="agent_blueprint",
        resource_id=str(bp.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"slug": bp.slug, "name": bp.name},
    )
    return bp


async def update_blueprint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    blueprint_id: UUID,
    data: BlueprintUpdate,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> AgentBlueprint:
    bp = await get_blueprint(db, tenant_id=tenant_id, blueprint_id=blueprint_id)
    updates = data.model_dump(exclude_unset=True)
    if "metadata" in updates:
        bp.metadata_ = updates.pop("metadata") or {}
    for key, value in updates.items():
        setattr(bp, key, value)
    await db.flush()
    await record_audit(
        db,
        tenant_id=tenant_id,
        action="blueprint.updated",
        resource_type="agent_blueprint",
        resource_id=str(bp.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail=updates,
    )
    return bp


async def delete_blueprint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    blueprint_id: UUID,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> None:
    bp = await get_blueprint(db, tenant_id=tenant_id, blueprint_id=blueprint_id)
    await record_audit(
        db,
        tenant_id=tenant_id,
        action="blueprint.deleted",
        resource_type="agent_blueprint",
        resource_id=str(bp.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"slug": bp.slug},
    )
    await db.delete(bp)
    await db.flush()


async def register_from_blueprint(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    blueprint_id: UUID,
    body: BlueprintRegisterRequest,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> tuple:
    """Upsert a registry agent using blueprint defaults + required identity/invoke."""
    bp = await get_blueprint(db, tenant_id=tenant_id, blueprint_id=blueprint_id)
    agent, created = await agent_registry.upsert_agent_by_external_id(
        db,
        tenant_id=tenant_id,
        data=AgentCreate(
            name=body.name,
            platform=bp.connector_type,
            framework=bp.framework,
            external_id=body.external_id,
            owner=body.owner,
            team=body.team,
            domain=body.domain or bp.default_domain,
            environment=body.environment,
            lifecycle_state="registered",
            risk_class=bp.default_risk_class,
            connection_id=body.connection_id,
            blueprint_id=bp.id,
            invoke_url=body.invoke_url,
            description=body.description or bp.description,
            metadata={
                "source": "blueprint",
                "blueprint_slug": bp.slug,
                **(body.metadata or {}),
            },
        ),
        actor_id=actor_id,
        actor_email=actor_email,
    )
    await db.refresh(agent)
    return agent, created, bp
