"""Reliability Center API — real execution failure signals."""

from fastapi import APIRouter, Query

from app.core.deps import AuthUser, DbSession
from app.schemas.reliability import ReliabilityOverview
from app.services import reliability as reliability_svc

router = APIRouter()


@router.get("/overview", response_model=ReliabilityOverview)
async def reliability_overview(
    db: DbSession,
    user: AuthUser,
    window_hours: int = Query(24, ge=1, le=336),
) -> ReliabilityOverview:
    return await reliability_svc.reliability_overview(
        db,
        tenant_id=user.tenant_id,
        window_hours=window_hours,
    )
