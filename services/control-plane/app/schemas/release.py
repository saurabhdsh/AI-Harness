"""Release train / promotion schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ReleaseTrainOut(ORMModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    description: str | None
    stages: list[Any]
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PromotionCreate(BaseModel):
    agent_id: UUID
    to_env: str = Field(min_length=1, max_length=64)
    train_slug: str | None = Field(default=None, description="Defaults to 'standard'")
    justification: str | None = None
    # Overrides — None means use train stage defaults
    require_evaluation: bool | None = None
    require_approval: bool | None = None


class GateResult(BaseModel):
    id: str
    type: str
    required: bool = True
    status: str  # pending | passed | failed | skipped
    detail: str | None = None


class PromotionOut(ORMModel):
    id: UUID
    tenant_id: UUID
    agent_id: UUID
    train_id: UUID | None
    from_env: str
    to_env: str
    status: str
    gates: list[Any]
    justification: str | None
    error: str | None
    requested_by: UUID | None
    approval_id: UUID | None
    completed_at: datetime | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime
    # hydrated for UI
    agent_name: str | None = None
    train_name: str | None = None


class ReleaseBoardEnv(BaseModel):
    environment: str
    agents: list[dict[str, Any]]


class ReleaseBoard(BaseModel):
    environments: list[ReleaseBoardEnv]
    trains: list[ReleaseTrainOut]
    open_promotions: list[PromotionOut]
