"""Cost and budget endpoints."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.deps import AuthUser, DbSession
from app.models.cost import Budget, CostRecord
from app.schemas.cost import BudgetOut, CostRecordOut, CostSummary

router = APIRouter()


@router.get("", response_model=list[CostRecordOut])
async def list_costs(
    db: DbSession,
    user: AuthUser,
    limit: int = 100,
) -> list[CostRecordOut]:
    result = await db.execute(
        select(CostRecord)
        .where(CostRecord.tenant_id == user.tenant_id)
        .order_by(CostRecord.created_at.desc())
        .limit(limit)
    )
    return [CostRecordOut.model_validate(r) for r in result.scalars().all()]


@router.get("/summary", response_model=CostSummary)
async def cost_summary(db: DbSession, user: AuthUser) -> CostSummary:
    result = await db.execute(
        select(
            func.coalesce(func.sum(CostRecord.cost_usd), 0.0),
            func.coalesce(func.sum(CostRecord.token_input), 0),
            func.coalesce(func.sum(CostRecord.token_output), 0),
            func.count(),
        ).where(CostRecord.tenant_id == user.tenant_id)
    )
    row = result.one()
    return CostSummary(
        total_cost_usd=float(row[0] or 0),
        total_token_input=int(row[1] or 0),
        total_token_output=int(row[2] or 0),
        records=int(row[3] or 0),
    )


@router.get("/budgets", response_model=list[BudgetOut])
async def list_budgets(db: DbSession, user: AuthUser) -> list[BudgetOut]:
    result = await db.execute(
        select(Budget).where(Budget.tenant_id == user.tenant_id)
    )
    return [BudgetOut.model_validate(b) for b in result.scalars().all()]
