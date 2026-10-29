"""Approval request endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import AuthUser, DbSession
from app.models.approval import ApprovalRequest
from app.schemas.approval import ApprovalCreate, ApprovalDecide, ApprovalOut
from app.services.audit import record_audit

router = APIRouter()


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(db: DbSession, user: AuthUser) -> list[ApprovalOut]:
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.tenant_id == user.tenant_id)
        .order_by(ApprovalRequest.created_at.desc())
    )
    return [ApprovalOut.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreate,
    db: DbSession,
    user: AuthUser,
) -> ApprovalOut:
    req = ApprovalRequest(
        tenant_id=user.tenant_id,
        agent_id=body.agent_id,
        requested_by=user.user_id,
        action=body.action,
        justification=body.justification,
        payload=body.payload,
        status="pending",
    )
    db.add(req)
    await db.flush()
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="approval.requested",
        resource_type="approval_request",
        resource_id=str(req.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"action": body.action},
    )
    return ApprovalOut.model_validate(req)


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide_approval(
    approval_id: UUID,
    body: ApprovalDecide,
    db: DbSession,
    user: AuthUser,
) -> ApprovalOut:
    req = await db.get(ApprovalRequest, approval_id)
    if req is None or req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be approved or rejected")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Approval already {req.status}")
    req.status = body.status
    req.decision_notes = body.decision_notes
    req.decided_by = user.user_id
    await db.flush()
    # Release Command: promote approvals complete/reject the linked promotion
    if req.action == "promote":
        from app.services import release as release_svc

        await release_svc.on_approval_decided(
            db,
            req,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    # Workflow Orchestration: resume / fail HITL-gated runs
    if req.action == "workflow_hitl":
        from app.workflows import service as wf_svc

        await wf_svc.on_hitl_decided(
            db,
            req,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    # Source-platform delete (beyond Agent 365 read-only)
    if req.action == "agent.delete_source" and body.status == "approved" and req.agent_id:
        from app.schemas.lifecycle import LifecycleActionRequest
        from app.services import lifecycle as lifecycle_svc

        payload = req.payload or {}
        await lifecycle_svc.run_lifecycle(
            db,
            tenant_id=user.tenant_id,
            agent_id=req.agent_id,
            operation="delete_source",
            body=LifecycleActionRequest(
                confirm_delete_source=True,
                create_approval=False,
                remove_from_registry=bool(payload.get("remove_from_registry")),
                justification=req.justification,
                alias_id=payload.get("alias_id"),
            ),
            actor_id=user.user_id,
            actor_email=user.email,
        )
    await db.refresh(req)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action=f"approval.{body.status}",
        resource_type="approval_request",
        resource_id=str(req.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"notes": body.decision_notes, "action": req.action},
    )
    return ApprovalOut.model_validate(req)
