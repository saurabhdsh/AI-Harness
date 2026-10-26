"""Execution list/get endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.core.deps import AuthUser, DbSession
from app.schemas.execution import ExecutionOut
from app.services import execution as execution_service

router = APIRouter()


@router.get("", response_model=list[ExecutionOut])
async def list_executions(
    db: DbSession,
    user: AuthUser,
    agent_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExecutionOut]:
    rows = await execution_service.list_executions(
        db,
        tenant_id=user.tenant_id,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    return [ExecutionOut.model_validate(r) for r in rows]


@router.get("/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    execution_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> ExecutionOut:
    try:
        row = await execution_service.get_execution(
            db, tenant_id=user.tenant_id, execution_id=execution_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExecutionOut.model_validate(row)
