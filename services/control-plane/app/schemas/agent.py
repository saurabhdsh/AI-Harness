"""Agent schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    platform: str = "generic"
    framework: str = "rest"
    external_id: str | None = None
    owner: str | None = None
    team: str | None = None
    domain: str | None = None
    environment: str = "dev"
    lifecycle_state: str = "draft"
    risk_class: str = "medium"
    connection_id: UUID | None = None
    invoke_url: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    name: str | None = None
    platform: str | None = None
    framework: str | None = None
    external_id: str | None = None
    owner: str | None = None
    team: str | None = None
    domain: str | None = None
    environment: str | None = None
    lifecycle_state: str | None = None
    risk_class: str | None = None
    health_status: str | None = None
    evaluation_status: str | None = None
    connection_id: UUID | None = None
    invoke_url: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class AgentOut(ORMModel):
    id: UUID
    tenant_id: UUID
    name: str
    platform: str
    framework: str
    external_id: str | None
    owner: str | None
    team: str | None
    domain: str | None
    environment: str
    lifecycle_state: str
    risk_class: str
    health_status: str
    evaluation_status: str
    connection_id: UUID | None
    invoke_url: str | None
    description: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class AgentInvokeRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class AgentInvokeResponse(BaseModel):
    execution_id: UUID
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None
    token_input: int | None = None
    token_output: int | None = None
    trace_id: str | None = None
    error: str | None = None
