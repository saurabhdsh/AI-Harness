"""Agent identity blueprints — Agent 365–style templates."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AuthUser, DbSession
from app.schemas.agent import AgentOut
from app.schemas.blueprint import (
    BlueprintCreate,
    BlueprintOut,
    BlueprintRegisterRequest,
    BlueprintUpdate,
)
from app.services import blueprints as blueprint_service

router = APIRouter()


@router.get("", response_model=list[BlueprintOut])
async def list_blueprints(db: DbSession, user: AuthUser) -> list[BlueprintOut]:
    rows = await blueprint_service.list_blueprints(db, tenant_id=user.tenant_id)
    return [BlueprintOut.model_validate(r) for r in rows]


@router.post("", response_model=BlueprintOut, status_code=status.HTTP_201_CREATED)
async def create_blueprint(
    body: BlueprintCreate,
    db: DbSession,
    user: AuthUser,
) -> BlueprintOut:
    try:
        bp = await blueprint_service.create_blueprint(
            db,
            tenant_id=user.tenant_id,
            data=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BlueprintOut.model_validate(bp)


@router.get("/{blueprint_id}", response_model=BlueprintOut)
async def get_blueprint(
    blueprint_id: UUID, db: DbSession, user: AuthUser
) -> BlueprintOut:
    try:
        bp = await blueprint_service.get_blueprint(
            db, tenant_id=user.tenant_id, blueprint_id=blueprint_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BlueprintOut.model_validate(bp)


@router.patch("/{blueprint_id}", response_model=BlueprintOut)
async def update_blueprint(
    blueprint_id: UUID,
    body: BlueprintUpdate,
    db: DbSession,
    user: AuthUser,
) -> BlueprintOut:
    try:
        bp = await blueprint_service.update_blueprint(
            db,
            tenant_id=user.tenant_id,
            blueprint_id=blueprint_id,
            data=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BlueprintOut.model_validate(bp)


@router.delete("/{blueprint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blueprint(
    blueprint_id: UUID, db: DbSession, user: AuthUser
) -> None:
    try:
        await blueprint_service.delete_blueprint(
            db,
            tenant_id=user.tenant_id,
            blueprint_id=blueprint_id,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{blueprint_id}/register",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register inventory agent from blueprint (external_id + invoke_url)",
)
async def register_from_blueprint(
    blueprint_id: UUID,
    body: BlueprintRegisterRequest,
    db: DbSession,
    user: AuthUser,
) -> AgentOut:
    try:
        agent, _created, _bp = await blueprint_service.register_from_blueprint(
            db,
            tenant_id=user.tenant_id,
            blueprint_id=blueprint_id,
            body=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AgentOut.model_validate(agent)
