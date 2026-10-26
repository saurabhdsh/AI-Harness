"""Cost and budget schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class CostRecordOut(ORMModel):
    id: UUID
    tenant_id: UUID
    agent_id: UUID | None
    execution_id: UUID | None
    cost_usd: float
    token_input: int
    token_output: int
    model_name: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    agent_name: str | None = None


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scope: Literal["tenant", "agent"] = "tenant"
    agent_id: UUID | None = None
    limit_usd: float = Field(gt=0)
    period: Literal["daily", "weekly", "monthly", "all_time"] = "monthly"
    alert_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    is_active: bool = True

    @model_validator(mode="after")
    def agent_required_for_agent_scope(self) -> "BudgetCreate":
        if self.scope == "agent" and self.agent_id is None:
            raise ValueError("agent_id is required when scope=agent")
        if self.scope == "tenant":
            self.agent_id = None
        return self


class BudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scope: Literal["tenant", "agent"] | None = None
    agent_id: UUID | None = None
    limit_usd: float | None = Field(default=None, gt=0)
    period: Literal["daily", "weekly", "monthly", "all_time"] | None = None
    alert_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    is_active: bool | None = None


class BudgetOut(ORMModel):
    id: UUID
    tenant_id: UUID
    name: str
    scope: str
    agent_id: UUID | None
    limit_usd: float
    spent_usd: float
    period: str
    alert_threshold: float
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # FinOps enrichment (period-aware, computed from CostRecords)
    computed_spent_usd: float = 0.0
    pct_used: float = 0.0
    remaining_usd: float = 0.0
    over_threshold: bool = False
    period_start: datetime | None = None
    agent_name: str | None = None


class CostSummary(BaseModel):
    total_cost_usd: float
    total_token_input: int
    total_token_output: int
    records: int
    rate_note: str = "Estimated placeholder rates — not provider invoices"
    budgets_over_threshold: int = 0
    active_budgets: int = 0
    repaired_records: int = 0
