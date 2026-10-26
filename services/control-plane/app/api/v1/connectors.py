"""Platform connector endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import AuthUser, DbSession
from app.models.connection import PlatformConnection
from app.schemas.connector import ConnectorCreate, ConnectorOut, ConnectorValidateResponse
from app.services import onboarding as onboarding_service
from app.services.audit import record_audit

router = APIRouter()


@router.get("", response_model=list[ConnectorOut])
async def list_connectors(db: DbSession, user: AuthUser) -> list[ConnectorOut]:
    result = await db.execute(
        select(PlatformConnection)
        .where(PlatformConnection.tenant_id == user.tenant_id)
        .order_by(PlatformConnection.created_at.desc())
    )
    return [ConnectorOut.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=ConnectorOut, status_code=status.HTTP_201_CREATED)
async def create_connector(
    body: ConnectorCreate,
    db: DbSession,
    user: AuthUser,
) -> ConnectorOut:
    try:
        conn = await onboarding_service.create_connection(
            db,
            tenant_id=user.tenant_id,
            name=body.name,
            connector_type=body.connector_type,
            base_url=body.base_url,
            secret_ref=body.secret_ref,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="connector.created",
        resource_type="platform_connection",
        resource_id=str(conn.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"connector_type": body.connector_type, "base_url": body.base_url},
    )
    return ConnectorOut.model_validate(conn)


@router.get("/{connector_id}", response_model=ConnectorOut)
async def get_connector(connector_id: UUID, db: DbSession, user: AuthUser) -> ConnectorOut:
    conn = await db.get(PlatformConnection, connector_id)
    if conn is None or conn.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return ConnectorOut.model_validate(conn)


@router.post("/{connector_id}/validate", response_model=ConnectorValidateResponse)
async def validate_connector(
    connector_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> ConnectorValidateResponse:
    try:
        ok, caps, count, error = await onboarding_service.validate_connection(
            db, tenant_id=user.tenant_id, connection_id=connector_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ConnectorValidateResponse(
        ok=ok,
        capabilities=caps,
        discovered_count=count,
        error=error,
    )
