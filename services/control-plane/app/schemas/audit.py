"""Audit event schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AuditEventOut(ORMModel):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    actor_id: UUID | None
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict[str, Any] = Field(default_factory=dict)
