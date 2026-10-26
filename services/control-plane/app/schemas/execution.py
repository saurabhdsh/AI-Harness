"""Execution and trace schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ExecutionOut(ORMModel):
    id: UUID
    tenant_id: UUID
    agent_id: UUID
    status: str
    request: dict[str, Any]
    response: dict[str, Any] | None
    latency_ms: float | None
    token_input: int | None
    token_output: int | None
    trace_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class TraceOut(ORMModel):
    id: UUID
    tenant_id: UUID
    execution_id: UUID
    spans: list[Any]
    status: str
    created_at: datetime
    updated_at: datetime
