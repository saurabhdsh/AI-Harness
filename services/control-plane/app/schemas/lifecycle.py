"""External agent lifecycle control schemas (beyond Agent 365 read-only)."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LifecycleActionRequest(BaseModel):
    """Optional payload for lifecycle operations."""

    justification: str | None = None
    version: str | None = Field(
        default=None, description="Target version for rollback / deploy alias"
    )
    alias_id: str | None = Field(
        default=None, description="Bedrock agent alias id (defaults to env / TSTALIASID)"
    )
    confirm_delete_source: bool = Field(
        default=False,
        description="Required true to delete the agent in the source platform",
    )
    remove_from_registry: bool = Field(
        default=False,
        description="After source delete, also remove KEEL registry row",
    )
    create_approval: bool = Field(
        default=True,
        description="For delete_source: create approval instead of executing immediately",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class LifecycleActionResult(BaseModel):
    agent_id: UUID
    operation: str
    status: str
    connector_type: str | None = None
    external_id: str | None = None
    lifecycle_state: str | None = None
    approval_id: UUID | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
