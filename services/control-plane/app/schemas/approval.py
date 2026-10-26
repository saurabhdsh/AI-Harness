"""Approval request schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ApprovalCreate(BaseModel):
    agent_id: UUID | None = None
    action: str
    justification: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecide(BaseModel):
    status: str  # approved | rejected
    decision_notes: str | None = None


class ApprovalOut(ORMModel):
    id: UUID
    tenant_id: UUID
    agent_id: UUID | None
    requested_by: UUID | None
    action: str
    status: str
    justification: str | None
    decision_notes: str | None
    decided_by: UUID | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
