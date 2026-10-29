"""External agent lifecycle — start/stop/restart/deploy/rollback/delete-from-source."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import UnsupportedOperationError
from app.connectors.registry import get_connector
from app.models.agent import Agent
from app.models.approval import ApprovalRequest
from app.models.connection import PlatformConnection
from app.schemas.lifecycle import LifecycleActionRequest, LifecycleActionResult
from app.services import registry as agent_registry
from app.services.audit import record_audit

LIFECYCLE_STATE = {
    "suspend": "suspended",
    "stop": "suspended",
    "resume": "registered",
    "start": "registered",
    "restart": "registered",
    "deploy": "registered",
    "rollback": "registered",
}


def _connector_for_agent(agent: Agent, conn: PlatformConnection | None):
    if conn is not None:
        return get_connector(
            conn.connector_type, base_url=conn.base_url, secret_ref=conn.secret_ref
        )
    # Fall back to platform/framework hint (e.g. synced bedrock without connection)
    ctype = (agent.platform or agent.framework or "generic_rest").lower()
    if ctype in {"bedrock", "aws"}:
        ctype = "aws_bedrock"
    base = ""
    if agent.invoke_url:
        base = agent.invoke_url.rsplit("/", 1)[0]
    return get_connector(ctype, base_url=base or f"connector://{ctype}")


async def _load(
    db: AsyncSession, *, tenant_id: UUID, agent_id: UUID
) -> tuple[Agent, PlatformConnection | None]:
    agent = await agent_registry.get_agent(db, tenant_id=tenant_id, agent_id=agent_id)
    conn = None
    if agent.connection_id:
        conn = await db.get(PlatformConnection, agent.connection_id)
        if conn is not None and conn.tenant_id != tenant_id:
            conn = None
    return agent, conn


async def run_lifecycle(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID,
    operation: str,
    body: LifecycleActionRequest | None = None,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
) -> LifecycleActionResult:
    body = body or LifecycleActionRequest()
    op = operation.strip().lower()
    # Aliases
    if op == "stop":
        op = "suspend"
    if op == "start":
        op = "resume"

    agent, conn = await _load(db, tenant_id=tenant_id, agent_id=agent_id)
    if not agent.external_id and op != "deploy":
        raise ValueError("Agent has no external_id — cannot run source-platform lifecycle")

    connector = _connector_for_agent(agent, conn)
    external_id = agent.external_id or ""

    # Destructive delete: optional approval gate
    if op == "delete_source":
        if not body.confirm_delete_source:
            raise ValueError("confirm_delete_source=true is required to delete in the source platform")
        if body.create_approval:
            approval = ApprovalRequest(
                tenant_id=tenant_id,
                agent_id=agent.id,
                requested_by=actor_id,
                action="agent.delete_source",
                status="pending",
                justification=body.justification
                or f"Delete {agent.name} ({external_id}) from {connector.connector_type}",
                payload={
                    "operation": "delete_source",
                    "external_id": external_id,
                    "connector_type": connector.connector_type,
                    "remove_from_registry": body.remove_from_registry,
                    "alias_id": body.alias_id,
                },
            )
            db.add(approval)
            await db.flush()
            await record_audit(
                db,
                tenant_id=tenant_id,
                action="lifecycle.delete_source_approval",
                resource_type="agent",
                resource_id=str(agent.id),
                actor_id=actor_id,
                actor_email=actor_email,
                detail={"approval_id": str(approval.id), "external_id": external_id},
            )
            return LifecycleActionResult(
                agent_id=agent.id,
                operation="delete_source",
                status="awaiting_approval",
                connector_type=connector.connector_type,
                external_id=external_id,
                lifecycle_state=agent.lifecycle_state,
                approval_id=approval.id,
                detail={"message": "Approve in Governance Center to execute source delete"},
            )

    detail: dict[str, Any] = {}
    try:
        if op == "suspend":
            detail = await connector.suspend(external_id)
        elif op == "resume":
            # Prefer snapshot restore for Bedrock if we stored one
            if hasattr(connector, "resume"):
                detail = await connector.resume(external_id)
            else:
                raise UnsupportedOperationError("resume", connector.connector_type)
        elif op == "restart":
            if hasattr(connector, "restart"):
                detail = await connector.restart(external_id)
            else:
                await connector.suspend(external_id)
                detail = await connector.resume(external_id)  # type: ignore[attr-defined]
                detail = {"operation": "restart", "composed": True, **(detail or {})}
        elif op == "deploy":
            payload = {
                "external_id": external_id,
                "agent_id": str(agent.id),
                "version": body.version,
                "alias_id": body.alias_id,
                **(body.metadata or {}),
            }
            detail = await connector.deploy(payload)
        elif op == "rollback":
            if not body.version:
                raise ValueError("version is required for rollback")
            detail = await connector.rollback(external_id, body.version)
        elif op == "delete_source":
            detail = await connector.delete_from_source(external_id)
            agent.lifecycle_state = "retired"
            meta = dict(agent.metadata_ or {})
            meta["source_deleted"] = True
            meta["source_delete_detail"] = detail
            agent.metadata_ = meta
            await db.flush()
            if body.remove_from_registry:
                await agent_registry.delete_agent(
                    db,
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    actor_id=actor_id,
                    actor_email=actor_email,
                )
                return LifecycleActionResult(
                    agent_id=agent_id,
                    operation=op,
                    status="completed",
                    connector_type=connector.connector_type,
                    external_id=external_id,
                    lifecycle_state="retired",
                    detail={**detail, "registry_removed": True},
                )
        else:
            raise ValueError(
                f"Unknown lifecycle operation '{operation}'. "
                "Use: start|stop|suspend|resume|restart|deploy|rollback|delete_source"
            )
    except UnsupportedOperationError:
        raise
    except AttributeError as exc:
        raise UnsupportedOperationError(op, getattr(connector, "connector_type", "unknown"), str(exc)) from exc

    # Update registry lifecycle + store Bedrock suspend snapshot when present
    new_state = LIFECYCLE_STATE.get(op)
    if new_state:
        agent.lifecycle_state = new_state
    meta = dict(agent.metadata_ or {})
    meta["last_lifecycle_op"] = op
    meta["last_lifecycle_detail"] = detail
    if op == "suspend" and isinstance(detail.get("snapshot"), dict):
        meta["bedrock_alias_snapshot"] = detail["snapshot"]
    agent.metadata_ = meta
    # health hint
    if op == "suspend":
        agent.health_status = "suspended"
    elif op in {"resume", "restart", "deploy", "rollback"}:
        agent.health_status = "unknown"
    await db.flush()

    await record_audit(
        db,
        tenant_id=tenant_id,
        action=f"lifecycle.{op}",
        resource_type="agent",
        resource_id=str(agent.id),
        actor_id=actor_id,
        actor_email=actor_email,
        detail={"external_id": external_id, "result": detail},
    )

    return LifecycleActionResult(
        agent_id=agent.id,
        operation=op,
        status="completed",
        connector_type=connector.connector_type,
        external_id=external_id,
        lifecycle_state=agent.lifecycle_state,
        detail=detail,
    )
