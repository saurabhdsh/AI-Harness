"""Audit event listing."""

from fastapi import APIRouter

from app.core.deps import AuthUser, DbSession
from app.schemas.audit import AuditEventOut
from app.services import audit as audit_service

router = APIRouter()


@router.get("", response_model=list[AuditEventOut])
async def list_audit_events(
    db: DbSession,
    user: AuthUser,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
) -> list[AuditEventOut]:
    events = await audit_service.list_audit_events(
        db,
        tenant_id=user.tenant_id,
        limit=limit,
        offset=offset,
        action=action,
    )
    return [AuditEventOut.model_validate(e) for e in events]
