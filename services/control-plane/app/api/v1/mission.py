"""Mission control overview — real DB aggregates."""

from fastapi import APIRouter

from app.core.deps import AuthUser, DbSession
from app.schemas.mission import MissionOverview
from app.services import observability

router = APIRouter()


@router.get("/overview", response_model=MissionOverview)
async def mission_overview(db: DbSession, user: AuthUser) -> MissionOverview:
    return await observability.mission_overview(db, tenant_id=user.tenant_id)
