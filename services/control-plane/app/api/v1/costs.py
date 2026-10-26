"""Cost and budget endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.deps import AuthUser, DbSession
from app.models.agent import Agent
from app.models.cost import Budget, CostRecord
from app.schemas.cost import (
    BudgetCreate,
    BudgetOut,
    BudgetUpdate,
    CostRecordOut,
    CostSummary,
)
from app.services import budget as budget_svc
from app.services.audit import record_audit

router = APIRouter()


def _require_admin(user: AuthUser) -> None:
    role = (user.role or "").lower()
    if role not in ("admin", "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to manage budgets",
        )


@router.get("", response_model=list[CostRecordOut])
async def list_costs(
    db: DbSession,
    user: AuthUser,
    limit: int = Query(100, ge=1, le=500),
    agent_id: UUID | None = None,
) -> list[CostRecordOut]:
    from app.services.costing import repair_zero_cost_records

    await repair_zero_cost_records(db, user.tenant_id)
    q = select(CostRecord).where(CostRecord.tenant_id == user.tenant_id)
    if agent_id:
        q = q.where(CostRecord.agent_id == agent_id)
    q = q.order_by(CostRecord.created_at.desc()).limit(limit)
    result = await db.execute(q)
    rows = list(result.scalars().all())
    # Attach agent names for FinOps table
    agent_ids = {r.agent_id for r in rows if r.agent_id}
    names: dict[UUID, str] = {}
    if agent_ids:
        agents = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
        names = {a.id: a.name for a in agents.scalars().all()}
    out: list[CostRecordOut] = []
    for r in rows:
        item = CostRecordOut.model_validate(r)
        # pydantic model may be frozen-ish — use model_copy
        item = item.model_copy(
            update={"agent_name": names.get(r.agent_id) if r.agent_id else None}
        )
        out.append(item)
    return out


@router.get("/summary", response_model=CostSummary)
async def cost_summary(db: DbSession, user: AuthUser) -> CostSummary:
    from app.services.costing import repair_zero_cost_records

    repaired = await repair_zero_cost_records(db, user.tenant_id)
    result = await db.execute(
        select(
            func.coalesce(func.sum(CostRecord.cost_usd), 0.0),
            func.coalesce(func.sum(CostRecord.token_input), 0),
            func.coalesce(func.sum(CostRecord.token_output), 0),
            func.count(),
        ).where(CostRecord.tenant_id == user.tenant_id)
    )
    row = result.one()
    budgets = await budget_svc.list_enriched_budgets(
        db, user.tenant_id, active_only=True
    )
    return CostSummary(
        total_cost_usd=float(row[0] or 0),
        total_token_input=int(row[1] or 0),
        total_token_output=int(row[2] or 0),
        records=int(row[3] or 0),
        budgets_over_threshold=sum(1 for b in budgets if b.over_threshold),
        active_budgets=len(budgets),
        repaired_records=repaired,
    )


@router.get("/budgets", response_model=list[BudgetOut])
async def list_budgets(
    db: DbSession,
    user: AuthUser,
    active_only: bool = False,
) -> list[BudgetOut]:
    return await budget_svc.list_enriched_budgets(
        db, user.tenant_id, active_only=active_only
    )


@router.get("/budgets/{budget_id}", response_model=BudgetOut)
async def get_budget(
    budget_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> BudgetOut:
    budget = await db.get(Budget, budget_id)
    if budget is None or budget.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Budget not found")
    return await budget_svc.enrich_budget(db, budget)


@router.post("/budgets", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def create_budget(
    body: BudgetCreate,
    db: DbSession,
    user: AuthUser,
) -> BudgetOut:
    _require_admin(user)
    if body.scope == "agent" and body.agent_id:
        agent = await db.get(Agent, body.agent_id)
        if agent is None or agent.tenant_id != user.tenant_id:
            raise HTTPException(status_code=400, detail="Agent not found in tenant")

    budget = Budget(
        tenant_id=user.tenant_id,
        name=body.name,
        scope=body.scope,
        agent_id=body.agent_id,
        limit_usd=body.limit_usd,
        spent_usd=0.0,
        period=body.period,
        alert_threshold=body.alert_threshold,
        is_active=body.is_active,
    )
    db.add(budget)
    await db.flush()
    await db.refresh(budget)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="budget.created",
        resource_type="budget",
        resource_id=str(budget.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={"name": budget.name, "limit_usd": budget.limit_usd, "period": budget.period},
    )
    return await budget_svc.enrich_budget(db, budget)


@router.patch("/budgets/{budget_id}", response_model=BudgetOut)
async def update_budget(
    budget_id: UUID,
    body: BudgetUpdate,
    db: DbSession,
    user: AuthUser,
) -> BudgetOut:
    _require_admin(user)
    budget = await db.get(Budget, budget_id)
    if budget is None or budget.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Budget not found")

    updates = body.model_dump(exclude_unset=True)
    if updates.get("scope") == "agent" and not (
        updates.get("agent_id") or budget.agent_id
    ):
        raise HTTPException(status_code=400, detail="agent_id required for agent scope")
    if updates.get("scope") == "tenant":
        updates["agent_id"] = None
    if updates.get("agent_id"):
        agent = await db.get(Agent, updates["agent_id"])
        if agent is None or agent.tenant_id != user.tenant_id:
            raise HTTPException(status_code=400, detail="Agent not found in tenant")

    for key, value in updates.items():
        setattr(budget, key, value)
    await db.flush()
    await db.refresh(budget)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="budget.updated",
        resource_type="budget",
        resource_id=str(budget.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail=updates,
    )
    return await budget_svc.enrich_budget(db, budget)


@router.delete("/budgets/{budget_id}", response_model=BudgetOut)
async def deactivate_budget(
    budget_id: UUID,
    db: DbSession,
    user: AuthUser,
) -> BudgetOut:
    """Soft-delete: mark budget inactive (keeps history)."""
    _require_admin(user)
    budget = await db.get(Budget, budget_id)
    if budget is None or budget.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Budget not found")
    budget.is_active = False
    await db.flush()
    await db.refresh(budget)
    await record_audit(
        db,
        tenant_id=user.tenant_id,
        action="budget.deactivated",
        resource_type="budget",
        resource_id=str(budget.id),
        actor_id=user.user_id,
        actor_email=user.email,
        detail={},
    )
    return await budget_svc.enrich_budget(db, budget)
