"""API v1 routers."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    approvals,
    audit,
    auth,
    connectors,
    costs,
    evaluations,
    executions,
    health,
    mission,
    onboarding,
    traces,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(connectors.router, prefix="/connectors", tags=["connectors"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(evaluations.router, prefix="/evaluations", tags=["evaluations"])
api_router.include_router(executions.router, prefix="/executions", tags=["executions"])
api_router.include_router(traces.router, prefix="/traces", tags=["traces"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
api_router.include_router(audit.router, prefix="/audit-events", tags=["audit"])
api_router.include_router(mission.router, prefix="/mission", tags=["mission"])
api_router.include_router(costs.router, prefix="/costs", tags=["costs"])
