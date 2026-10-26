"""Trace endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.core.deps import AuthUser, DbSession
from app.schemas.execution import TraceOut
from app.services import observability

router = APIRouter()


@router.get("/{trace_id}", response_model=TraceOut)
async def get_trace(trace_id: UUID, db: DbSession, user: AuthUser) -> TraceOut:
    try:
        trace = await observability.get_trace(
            db, tenant_id=user.tenant_id, trace_id=trace_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TraceOut.model_validate(trace)
