"""Skill catalog seeding and invoke payload helpers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import AgentSkill, Skill
from app.skills.catalog import BUILTIN_SKILLS


async def ensure_builtin_skills(db: AsyncSession, tenant_id: UUID) -> int:
    """Idempotently seed built-in skills for a tenant. Returns count created."""
    created = 0
    for spec in BUILTIN_SKILLS:
        existing = await db.scalar(
            select(Skill).where(
                Skill.tenant_id == tenant_id,
                Skill.slug == spec["slug"],
                Skill.version == spec["version"],
            )
        )
        if existing:
            continue
        db.add(
            Skill(
                tenant_id=tenant_id,
                slug=spec["slug"],
                name=spec["name"],
                domain=spec["domain"],
                version=spec["version"],
                description=spec.get("description"),
                instructions=spec["instructions"],
                input_schema=spec.get("input_schema") or {},
                output_schema=spec.get("output_schema") or {},
                eval_suite=spec.get("eval_suite") or {},
                risk_class=spec.get("risk_class") or "medium",
                tags=spec.get("tags") or [],
                sample_input=spec.get("sample_input") or {},
                is_active=True,
                is_builtin=True,
            )
        )
        created += 1
    if created:
        await db.flush()
    return created


async def get_agent_skills_payload(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    skill_slug: str | None = None,
) -> list[dict]:
    """Return attached skill payloads for invoke/eval injection."""
    q = (
        select(Skill, AgentSkill)
        .join(AgentSkill, AgentSkill.skill_id == Skill.id)
        .where(
            AgentSkill.tenant_id == tenant_id,
            AgentSkill.agent_id == agent_id,
            AgentSkill.is_active.is_(True),
            Skill.is_active.is_(True),
        )
    )
    if skill_slug:
        q = q.where(Skill.slug == skill_slug)
    rows = (await db.execute(q)).all()
    payload: list[dict] = []
    for skill, attachment in rows:
        payload.append(
            {
                "id": str(skill.id),
                "slug": skill.slug,
                "name": skill.name,
                "domain": skill.domain,
                "version": skill.version,
                "instructions": skill.instructions,
                "input_schema": skill.input_schema or {},
                "output_schema": skill.output_schema or {},
                "risk_class": skill.risk_class,
                "attachment_config": attachment.config or {},
            }
        )
    return payload


def format_skills_system_block(skills: list[dict]) -> str:
    """Compose a system prompt block from attached skills."""
    if not skills:
        return ""
    parts = ["# Attached enterprise skills", "Follow the active skill contract(s) below."]
    for s in skills:
        parts.append(f"\n## Skill: {s['name']} (`{s['slug']}` v{s['version']})")
        parts.append(s.get("instructions") or "")
        if s.get("output_schema"):
            parts.append(f"Expected output shape: {s['output_schema']}")
    return "\n".join(parts)
