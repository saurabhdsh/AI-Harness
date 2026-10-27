"""Skill Forge — catalog and agent attachments."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.deps import AuthUser, DbSession
from app.models.agent import Agent
from app.models.skill import AgentSkill, Skill
from app.schemas.skill import (
    AgentSkillAttach,
    AgentSkillOut,
    SkillCreate,
    SkillOut,
    SkillSeedResult,
    SkillUpdate,
)
from app.services.audit import record_audit
from app.skills.service import ensure_builtin_skills

router = APIRouter()


async def _seed_if_empty(db: DbSession, tenant_id: UUID) -> None:
    count = await db.scalar(
        select(func.count()).select_from(Skill).where(Skill.tenant_id == tenant_id)
    )
    if not count:
        await ensure_builtin_skills(db, tenant_id)


@router.get("", response_model=list[SkillOut])
async def list_skills(
    db: DbSession,
    user: AuthUser,
    domain: str | None = None,
    active_only: bool = True,
) -> list[SkillOut]:
    await _seed_if_empty(db, user.tenant_id)
    q = select(Skill).where(Skill.tenant_id == user.tenant_id)
    if domain:
        q = q.where(Skill.domain == domain.upper())
    if active_only:
        q = q.where(Skill.is_active.is_(True))
    q = q.order_by(Skill.domain, Skill.name)
    rows = (await db.execute(q)).scalars().all()
    return [SkillOut.model_validate(r) for r in rows]


@router.post("/seed", response_model=SkillSeedResult)
async def seed_skills(db: DbSession, user: AuthUser) -> SkillSeedResult:
    created = await ensure_builtin_skills(db, user.tenant_id)
    total = await db.scalar(
        select(func.count()).select_from(Skill).where(Skill.tenant_id == user.tenant_id)
    )
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="skills.seeded",
        resource_type="skill",
        resource_id=None,
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"created": created, "total": total},
    )
    return SkillSeedResult(created=created, total=int(total or 0))


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def create_skill(
    body: SkillCreate,
    db: DbSession,
    user: AuthUser,
) -> SkillOut:
    existing = await db.scalar(
        select(Skill).where(
            Skill.tenant_id == user.tenant_id,
            Skill.slug == body.slug,
            Skill.version == body.version,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Skill slug+version already exists")
    skill = Skill(
        tenant_id=user.tenant_id,
        slug=body.slug,
        name=body.name,
        domain=body.domain.upper(),
        version=body.version,
        description=body.description,
        instructions=body.instructions,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        eval_suite=body.eval_suite,
        risk_class=body.risk_class,
        tags=body.tags,
        sample_input=body.sample_input,
        is_active=body.is_active,
        is_builtin=False,
    )
    db.add(skill)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="skill.created",
        resource_type="skill",
        resource_id=str(skill.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"slug": skill.slug},
    )
    return SkillOut.model_validate(skill)


# Agent attachment routes BEFORE /{skill_id} so "by-agent" is not parsed as a UUID.
@router.get("/by-agent/{agent_id}", response_model=list[AgentSkillOut])
async def list_agent_skills(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    active_only: bool = Query(True),
) -> list[AgentSkillOut]:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    q = select(AgentSkill).where(
        AgentSkill.tenant_id == user.tenant_id,
        AgentSkill.agent_id == agent_id,
    )
    if active_only:
        q = q.where(AgentSkill.is_active.is_(True))
    attachments = (await db.execute(q)).scalars().all()
    out: list[AgentSkillOut] = []
    for a in attachments:
        skill = await db.get(Skill, a.skill_id)
        item = AgentSkillOut.model_validate(a)
        if skill and skill.tenant_id == user.tenant_id:
            item = item.model_copy(update={"skill": SkillOut.model_validate(skill)})
        out.append(item)
    return out


@router.post(
    "/by-agent/{agent_id}",
    response_model=AgentSkillOut,
    status_code=status.HTTP_201_CREATED,
)
async def attach_skill(
    agent_id: UUID,
    body: AgentSkillAttach,
    db: DbSession,
    user: AuthUser,
) -> AgentSkillOut:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    skill = await db.get(Skill, body.skill_id)
    if skill is None or skill.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Skill not found")

    existing = await db.scalar(
        select(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_id == body.skill_id,
        )
    )
    if existing:
        existing.is_active = body.is_active
        existing.config = body.config
        existing.attached_by = user.user_id
        await db.flush()
        item = AgentSkillOut.model_validate(existing)
        return item.model_copy(update={"skill": SkillOut.model_validate(skill)})

    attachment = AgentSkill(
        tenant_id=user.tenant_id,
        agent_id=agent_id,
        skill_id=body.skill_id,
        config=body.config,
        is_active=body.is_active,
        attached_by=user.user_id,
    )
    db.add(attachment)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="skill.attached",
        resource_type="agent",
        resource_id=str(agent_id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"skill_id": str(skill.id), "slug": skill.slug},
    )
    item = AgentSkillOut.model_validate(attachment)
    return item.model_copy(update={"skill": SkillOut.model_validate(skill)})


@router.delete("/by-agent/{agent_id}/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_skill(
    agent_id: UUID,
    skill_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> None:
    attachment = await db.scalar(
        select(AgentSkill).where(
            AgentSkill.tenant_id == user.tenant_id,
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_id == skill_id,
        )
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await db.delete(attachment)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="skill.detached",
        resource_type="agent",
        resource_id=str(agent_id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"skill_id": str(skill_id)},
    )


@router.get("/{skill_id}", response_model=SkillOut)
async def get_skill(skill_id: UUID, db: DbSession, user: AuthUser) -> SkillOut:
    skill = await db.get(Skill, skill_id)
    if skill is None or skill.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillOut.model_validate(skill)


@router.patch("/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: UUID,
    body: SkillUpdate,
    db: DbSession,
    user: AuthUser,
) -> SkillOut:
    skill = await db.get(Skill, skill_id)
    if skill is None or skill.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Skill not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(skill, k, v)
    await db.flush()
    await db.refresh(skill)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="skill.updated",
        resource_type="skill",
        resource_id=str(skill.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"fields": list(data.keys())},
    )
    return SkillOut.model_validate(skill)
