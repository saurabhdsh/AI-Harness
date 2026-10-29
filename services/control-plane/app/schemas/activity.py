"""Agent activity / observability schemas (Agent 365 Activity parity)."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ActivityDayOut(ORMModel):
    id: UUID
    agent_id: UUID
    day: date
    source: str
    sessions: int
    exceptions: int
    runtime_seconds: float
    unique_users: int
    tool_calls: int
    invocations: int
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    last_collected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentActivitySummary(BaseModel):
    agent_id: UUID
    window_days: int = 30
    sessions: int = 0
    exceptions: int = 0
    runtime_seconds: float = 0.0
    runtime_hours: float = 0.0
    unique_users: int = 0
    tool_calls: int = 0
    invocations: int = 0
    by_source: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    daily: list[ActivityDayOut] = Field(default_factory=list)
    note: str | None = None


class ActivityCollectResult(BaseModel):
    connection_id: UUID | None = None
    agent_id: UUID | None = None
    status: str
    snapshots_upserted: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
