"""Cost and budget schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

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


class CostSummary(BaseModel):
    total_cost_usd: float
    total_token_input: int
    total_token_output: int
    records: int
