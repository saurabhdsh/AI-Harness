"""Immutable audit event writer."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


async def record_audit(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        actor_email=actor_email,
        detail=detail or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(event)
    await db.flush()
    return event


async def list_audit_events(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
) -> list[AuditEvent]:
    from sqlalchemy import select

    stmt = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    result = await db.execute(stmt)
    return list(result.scalars().all())
