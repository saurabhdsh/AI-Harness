"""Workflow Orchestration schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class WorkflowDefinitionOut(ORMModel):
    id: UUID
    tenant_id: UUID
    slug: str
    name: str
    description: str | None
    domain: str
    version: str
    graph: dict[str, Any]
    sample_input: dict[str, Any]
    tags: list[Any]
    is_active: bool
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    hitl_count: int = 0


class WorkflowStepOut(ORMModel):
    id: UUID
    run_id: UUID
    node_id: str
    node_type: str
    label: str
    seq: int
    status: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    error: str | None
    agent_id: UUID | None
    execution_id: UUID | None
    approval_id: UUID | None
    latency_ms: float | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunOut(ORMModel):
    id: UUID
    tenant_id: UUID
    definition_id: UUID
    name: str
    status: str
    input_payload: dict[str, Any]
    context: dict[str, Any]
    agent_bindings: dict[str, Any]
    current_node_id: str | None
    error: str | None
    started_by: UUID | None
    pending_approval_id: UUID | None
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepOut] = Field(default_factory=list)
    definition_name: str | None = None
    definition_slug: str | None = None
    definition_domain: str | None = None


class WorkflowStartRequest(BaseModel):
    definition_id: UUID | None = None
    slug: str | None = None
    name: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    # node_id → agent_id (string uuid)
    agent_bindings: dict[str, str] = Field(default_factory=dict)


class WorkflowSeedResult(BaseModel):
    created: int
    total: int
