"""API v1 routers."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    approvals,
    audit,
    auth,
    blueprints,
    connectors,
    costs,
    evaluations,
    executions,
    health,
    mission,
    onboarding,
    otel,
    releases,
    reliability,
    skills,
    traces,
    workflows,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(blueprints.router, prefix="/blueprints", tags=["blueprints"])
api_router.include_router(connectors.router, prefix="/connectors", tags=["connectors"])
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(evaluations.router, prefix="/evaluations", tags=["evaluations"])
api_router.include_router(executions.router, prefix="/executions", tags=["executions"])
api_router.include_router(traces.router, prefix="/traces", tags=["traces"])
api_router.include_router(otel.router, prefix="/otel", tags=["otel"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
api_router.include_router(releases.router, prefix="/releases", tags=["releases"])
api_router.include_router(audit.router, prefix="/audit-events", tags=["audit"])
api_router.include_router(mission.router, prefix="/mission", tags=["mission"])
api_router.include_router(costs.router, prefix="/costs", tags=["costs"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(reliability.router, prefix="/reliability", tags=["reliability"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
