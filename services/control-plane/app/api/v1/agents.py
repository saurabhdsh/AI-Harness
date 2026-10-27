"""Agent CRUD, capabilities, and invoke."""

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
from app.services import execution as execution_service
from app.services import registry as agent_registry

router = APIRouter()


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
    "/{agent_id}/deploy",
    responses={501: {"model": ErrorOut}},
)
async def deploy_agent(agent_id: UUID, db: DbSession, user: AuthUser) -> dict:
    """Explicit unsupported path for connectors that do not implement deploy."""
    try:
        agent = await agent_registry.get_agent(
            db, tenant_id=user.tenant_id, agent_id=agent_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not agent.connection_id:
        raise HTTPException(
            status_code=501,
            detail={
                "detail": "Deploy requires a platform connection",
                "error_type": "UnsupportedOperationError",
                "operation": "deploy",
                "connector_type": agent.framework,
            },
        )

    conn = await db.get(PlatformConnection, agent.connection_id)
    if conn is None or conn.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Connection not found")

    connector = get_connector(
        conn.connector_type, base_url=conn.base_url, secret_ref=conn.secret_ref
    )
    try:
        return await connector.deploy({"agent_id": str(agent.id)})
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
