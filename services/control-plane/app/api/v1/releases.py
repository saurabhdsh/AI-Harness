"""Release Command API — trains, promotions, board."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import AuthUser, DbSession
from app.models.agent import Agent
from app.models.release import ReleaseTrain
from app.schemas.release import (
    PromotionCreate,
    PromotionOut,
    ReleaseBoard,
    ReleaseBoardEnv,
    ReleaseTrainOut,
)
from app.services import release as release_svc

router = APIRouter()


def _promo_out(
    promo,
    *,
    agent_name: str | None = None,
    train_name: str | None = None,
) -> PromotionOut:
    out = PromotionOut.model_validate(promo)
    out.agent_name = agent_name or (promo.metadata_ or {}).get("agent_name")
    out.train_name = train_name
    return out


@router.get("/trains", response_model=list[ReleaseTrainOut])
async def list_trains(db: DbSession, user: AuthUser) -> list[ReleaseTrainOut]:
    trains = await release_svc.list_trains(db, user.tenant_id)
    return [ReleaseTrainOut.model_validate(t) for t in trains]


@router.get("/board", response_model=ReleaseBoard)
async def release_board(db: DbSession, user: AuthUser) -> ReleaseBoard:
    board = await release_svc.build_board(db, user.tenant_id)
    agents_by_id: dict = board["agents_by_id"]
    trains_by_id: dict = board["trains_by_id"]
    open_out = []
    for p in board["open_promotions"]:
        agent = agents_by_id.get(str(p.agent_id))
        train = trains_by_id.get(str(p.train_id)) if p.train_id else None
        open_out.append(
            _promo_out(
                p,
                agent_name=agent.name if agent else None,
                train_name=train.name if train else None,
            )
        )
    return ReleaseBoard(
        environments=[ReleaseBoardEnv(**e) for e in board["environments"]],
        trains=[ReleaseTrainOut.model_validate(t) for t in board["trains"]],
        open_promotions=open_out,
    )


@router.get("/promotions", response_model=list[PromotionOut])
async def list_promotions(
    db: DbSession,
    user: AuthUser,
    status_filter: str | None = Query(None, alias="status"),
    agent_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[PromotionOut]:
    promos = await release_svc.list_promotions(
        db, user.tenant_id, status=status_filter, agent_id=agent_id, limit=limit
    )
    out: list[PromotionOut] = []
    for p in promos:
        agent = await db.get(Agent, p.agent_id)
        train = await db.get(ReleaseTrain, p.train_id) if p.train_id else None
        out.append(
            _promo_out(
                p,
                agent_name=agent.name if agent else None,
                train_name=train.name if train else None,
            )
        )
    return out


@router.get("/promotions/{promotion_id}", response_model=PromotionOut)
async def get_promotion(
    promotion_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> PromotionOut:
    promo = await release_svc.get_promotion(db, user.tenant_id, promotion_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    agent = await db.get(Agent, promo.agent_id)
    train = await db.get(ReleaseTrain, promo.train_id) if promo.train_id else None
    return _promo_out(
        promo,
        agent_name=agent.name if agent else None,
        train_name=train.name if train else None,
    )


@router.post(
    "/promotions",
    response_model=PromotionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_promotion(
    body: PromotionCreate,
    db: DbSession,
    user: AuthUser,
) -> PromotionOut:
    try:
        promo = await release_svc.create_promotion(
            db,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            user_email=user.email,
            data=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    agent = await db.get(Agent, promo.agent_id)
    train = await db.get(ReleaseTrain, promo.train_id) if promo.train_id else None
    return _promo_out(
        promo,
        agent_name=agent.name if agent else None,
        train_name=train.name if train else None,
    )


@router.post("/promotions/{promotion_id}/cancel", response_model=PromotionOut)
async def cancel_promotion(
    promotion_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> PromotionOut:
    promo = await release_svc.get_promotion(db, user.tenant_id, promotion_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    try:
        promo = await release_svc.cancel_promotion(
            db,
            promo,
            actor_id=user.user_id,
            actor_email=user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    agent = await db.get(Agent, promo.agent_id)
    train = await db.get(ReleaseTrain, promo.train_id) if promo.train_id else None
    return _promo_out(
        promo,
        agent_name=agent.name if agent else None,
        train_name=train.name if train else None,
    )


@router.post("/promotions/{promotion_id}/approve", response_model=PromotionOut)
async def approve_promotion_inline(
    promotion_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> PromotionOut:
    """Approve the linked HITL gate and complete the promotion."""
    from app.models.approval import ApprovalRequest
    from app.services import release as release_svc_inner

    promo = await release_svc.get_promotion(db, user.tenant_id, promotion_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    if not promo.approval_id:
        raise HTTPException(status_code=400, detail="Promotion has no pending approval")
    if promo.status != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"Promotion is {promo.status}")

    approval = await db.get(ApprovalRequest, promo.approval_id)
    if approval is None or approval.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Linked approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Approval already {approval.status}")

    approval.status = "approved"
    approval.decision_notes = "Approved from Release Command"
    approval.decided_by = user.user_id
    await db.flush()
    promo = await release_svc_inner.on_approval_decided(
        db,
        approval,
        actor_id=user.user_id,
        actor_email=user.email,
    )
    if promo is None:
        raise HTTPException(status_code=500, detail="Promotion side-effect failed")
    agent = await db.get(Agent, promo.agent_id)
    train = await db.get(ReleaseTrain, promo.train_id) if promo.train_id else None
    return _promo_out(
        promo,
        agent_name=agent.name if agent else None,
        train_name=train.name if train else None,
    )


@router.post("/promotions/{promotion_id}/reject", response_model=PromotionOut)
async def reject_promotion_inline(
    promotion_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> PromotionOut:
    from app.models.approval import ApprovalRequest

    promo = await release_svc.get_promotion(db, user.tenant_id, promotion_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    if not promo.approval_id:
        raise HTTPException(status_code=400, detail="Promotion has no pending approval")

    approval = await db.get(ApprovalRequest, promo.approval_id)
    if approval is None or approval.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Linked approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Approval already {approval.status}")

    approval.status = "rejected"
    approval.decision_notes = "Rejected from Release Command"
    approval.decided_by = user.user_id
    await db.flush()
    promo = await release_svc.on_approval_decided(
        db,
        approval,
        actor_id=user.user_id,
        actor_email=user.email,
    )
    if promo is None:
        raise HTTPException(status_code=500, detail="Promotion side-effect failed")
    agent = await db.get(Agent, promo.agent_id)
    train = await db.get(ReleaseTrain, promo.train_id) if promo.train_id else None
    return _promo_out(
        promo,
        agent_name=agent.name if agent else None,
        train_name=train.name if train else None,
    )
