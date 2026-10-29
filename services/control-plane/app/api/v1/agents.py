"""Agent CRUD, capabilities, invoke, and source-platform lifecycle controls."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.connectors.base import UnsupportedOperationError
from app.connectors.registry import get_connector
from app.core.deps import AuthUser, DbSession
from app.models.connection import PlatformConnection
from app.schemas.agent import (
    AgentCreate,
    AgentInvokeRequest,
    AgentInvokeResponse,
    AgentOut,
    AgentUpdate,
)
from app.schemas.common import ErrorOut
from app.schemas.activity import AgentActivitySummary
from app.schemas.lifecycle import LifecycleActionRequest, LifecycleActionResult
from app.services import activity as activity_service
from app.services import execution as execution_service
from app.services import lifecycle as lifecycle_service
from app.services import registry as agent_registry

router = APIRouter()


def _lifecycle_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, UnsupportedOperationError):
        return HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "detail": str(exc),
                "error_type": "UnsupportedOperationError",
                "operation": exc.operation,
                "connector_type": exc.connector_type,
            },
        )
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (ValueError, PermissionError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


async def _run_lifecycle(
    agent_id: UUID,
    operation: str,
    body: LifecycleActionRequest | None,
    db: DbSession,
    user: AuthUser,
) -> LifecycleActionResult:
    try:
        return await lifecycle_service.run_lifecycle(
            db,
            tenant_id=user.tenant_id,
            agent_id=agent_id,
            operation=operation,
            body=body or LifecycleActionRequest(),
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except Exception as exc:  # noqa: BLE001
        raise _lifecycle_http_error(exc) from exc


@router.get("", response_model=list[AgentOut])
async def list_agents(
    db: DbSession,
    user: AuthUser,
    limit: int = 100,
    offset: int = 0,
) -> list[AgentOut]:
    agents = await agent_registry.list_agents(
        db, tenant_id=user.tenant_id, limit=limit, offset=offset
    )
    return [AgentOut.model_validate(a) for a in agents]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    db: DbSession,
    user: AuthUser,
) -> AgentOut:
    try:
        agent = await agent_registry.create_agent(
            db,
            tenant_id=user.tenant_id,
            data=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AgentOut.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: UUID, db: DbSession, user: AuthUser) -> AgentOut:
    try:
        agent = await agent_registry.get_agent(
            db, tenant_id=user.tenant_id, agent_id=agent_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AgentOut.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    db: DbSession,
    user: AuthUser,
) -> AgentOut:
    try:
        agent = await agent_registry.update_agent(
            db,
            tenant_id=user.tenant_id,
            agent_id=agent_id,
            data=body,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AgentOut.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: UUID, db: DbSession, user: AuthUser) -> None:
    try:
        await agent_registry.delete_agent(
            db,
            tenant_id=user.tenant_id,
            agent_id=agent_id,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{agent_id}/activity", response_model=AgentActivitySummary)
async def get_agent_activity(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    window_days: int = 30,
) -> AgentActivitySummary:
    """Agent 365–style Activity: sessions, exceptions, runtime, users."""
    try:
        return await activity_service.agent_activity_summary(
            db,
            tenant_id=user.tenant_id,
            agent_id=agent_id,
            window_days=max(1, min(window_days, 90)),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{agent_id}/capabilities")
async def get_capabilities(agent_id: UUID, db: DbSession, user: AuthUser) -> dict:
    try:
        agent = await agent_registry.get_agent(
            db, tenant_id=user.tenant_id, agent_id=agent_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if agent.connection_id:
        conn = await db.get(PlatformConnection, agent.connection_id)
        if conn is None or conn.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Connection not found")
        connector = get_connector(
            conn.connector_type, base_url=conn.base_url, secret_ref=conn.secret_ref
        )
    else:
        if not agent.invoke_url:
            raise HTTPException(
                status_code=400,
                detail="Agent has no connection or invoke_url for capabilities",
            )
        base = agent.invoke_url.rsplit("/", 1)[0]
        ctype = agent.framework if agent.framework in ("langgraph", "rest", "generic_rest") else "generic_rest"
        connector = get_connector(ctype, base_url=base)

    caps = await connector.get_capabilities()
    return caps.model_dump()


@router.post(
    "/{agent_id}/invoke",
    response_model=AgentInvokeResponse,
    responses={501: {"model": ErrorOut}},
)
async def invoke_agent(
    agent_id: UUID,
    body: AgentInvokeRequest,
    db: DbSession,
    user: AuthUser,
) -> AgentInvokeResponse:
    try:
        execution = await execution_service.invoke_agent(
            db,
            tenant_id=user.tenant_id,
            agent_id=agent_id,
            input_payload=body.input,
            config=body.config,
            actor_id=user.user_id,
            actor_email=user.email,
            skill_slug=body.skill_slug,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnsupportedOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "detail": str(exc),
                "error_type": "UnsupportedOperationError",
                "operation": exc.operation,
                "connector_type": exc.connector_type,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AgentInvokeResponse(
        execution_id=execution.id,
        status=execution.status,
        output=execution.response or {},
        latency_ms=execution.latency_ms,
        token_input=execution.token_input,
        token_output=execution.token_output,
        trace_id=execution.trace_id,
        error=execution.error,
    )


@router.post(
    "/{agent_id}/lifecycle/{operation}",
    response_model=LifecycleActionResult,
    responses={400: {"model": ErrorOut}, 501: {"model": ErrorOut}},
    summary="Source-platform lifecycle: start|stop|suspend|resume|restart|deploy|rollback|delete_source",
)
async def agent_lifecycle(
    agent_id: UUID,
    operation: str,
    db: DbSession,
    user: AuthUser,
    body: LifecycleActionRequest | None = None,
) -> LifecycleActionResult:
    """KEEL goes beyond Agent 365 read-only connected platforms when the connector supports writes."""
    return await _run_lifecycle(agent_id, operation, body, db, user)


@router.post("/{agent_id}/start", response_model=LifecycleActionResult)
async def start_agent(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    body: LifecycleActionRequest | None = None,
) -> LifecycleActionResult:
    return await _run_lifecycle(agent_id, "start", body, db, user)


@router.post("/{agent_id}/stop", response_model=LifecycleActionResult)
async def stop_agent(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    body: LifecycleActionRequest | None = None,
) -> LifecycleActionResult:
    return await _run_lifecycle(agent_id, "stop", body, db, user)


@router.post("/{agent_id}/restart", response_model=LifecycleActionResult)
async def restart_agent(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    body: LifecycleActionRequest | None = None,
) -> LifecycleActionResult:
    return await _run_lifecycle(agent_id, "restart", body, db, user)


@router.post(
    "/{agent_id}/deploy",
    response_model=LifecycleActionResult,
    responses={501: {"model": ErrorOut}},
)
async def deploy_agent(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    body: LifecycleActionRequest | None = None,
) -> LifecycleActionResult:
    return await _run_lifecycle(agent_id, "deploy", body, db, user)


@router.post(
    "/{agent_id}/rollback",
    response_model=LifecycleActionResult,
    responses={501: {"model": ErrorOut}},
)
async def rollback_agent(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    body: LifecycleActionRequest | None = None,
) -> LifecycleActionResult:
    return await _run_lifecycle(agent_id, "rollback", body, db, user)


@router.post(
    "/{agent_id}/delete-source",
    response_model=LifecycleActionResult,
    responses={400: {"model": ErrorOut}, 501: {"model": ErrorOut}},
    summary="Delete agent in the source platform (approval by default)",
)
async def delete_agent_from_source(
    agent_id: UUID,
    db: DbSession,
    user: AuthUser,
    body: LifecycleActionRequest | None = None,
) -> LifecycleActionResult:
    req = body or LifecycleActionRequest()
    if not req.confirm_delete_source:
        req = req.model_copy(update={"confirm_delete_source": True})
    return await _run_lifecycle(agent_id, "delete_source", req, db, user)
