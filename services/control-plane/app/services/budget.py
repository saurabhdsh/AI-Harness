"""Budget helpers — period windows and spend computation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.cost import Budget, CostRecord
from app.schemas.cost import BudgetOut


def period_start(period: str, *, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    p = (period or "monthly").lower()
    if p in ("all", "all_time", "lifetime"):
        return None
    if p == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "weekly":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start - timedelta(days=start.weekday())
    # monthly default
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def sum_spend(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: UUID | None,
    since: datetime | None,
) -> float:
    q = select(func.coalesce(func.sum(CostRecord.cost_usd), 0.0)).where(
        CostRecord.tenant_id == tenant_id
    )
    if agent_id is not None:
        q = q.where(CostRecord.agent_id == agent_id)
    if since is not None:
        q = q.where(CostRecord.created_at >= since)
    result = await db.execute(q)
    return float(result.scalar_one() or 0.0)


async def enrich_budget(db: AsyncSession, budget: Budget) -> BudgetOut:
    since = period_start(budget.period)
    agent_filter = budget.agent_id if (budget.scope or "").lower() == "agent" else None
    spent = await sum_spend(
        db,
        tenant_id=budget.tenant_id,
        agent_id=agent_filter,
        since=since,
    )
    limit = float(budget.limit_usd or 0) or 0.0
    pct = (spent / limit) if limit > 0 else 0.0
    agent_name = None
    if budget.agent_id:
        agent = await db.get(Agent, budget.agent_id)
        agent_name = agent.name if agent else None

    out = BudgetOut.model_validate(budget)
    out.spent_usd = spent  # surface live spend (not stale column)
    out.computed_spent_usd = spent
    out.pct_used = round(pct, 4)
    out.remaining_usd = round(max(limit - spent, 0.0), 6)
    out.over_threshold = pct >= float(budget.alert_threshold or 0.8)
    out.period_start = since
    out.agent_name = agent_name
    return out


async def list_enriched_budgets(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    active_only: bool = False,
) -> list[BudgetOut]:
    q = select(Budget).where(Budget.tenant_id == tenant_id)
    if active_only:
        q = q.where(Budget.is_active.is_(True))
    q = q.order_by(Budget.created_at.desc())
    result = await db.execute(q)
    budgets = list(result.scalars().all())
    return [await enrich_budget(db, b) for b in budgets]
