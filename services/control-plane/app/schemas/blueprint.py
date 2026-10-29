"""Agent identity blueprint schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class BlueprintCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str | None = None
    connector_type: str = "generic_rest"
    framework: str = "rest"
    default_domain: str | None = None
    default_risk_class: str = "medium"
    permissions: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BlueprintUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    connector_type: str | None = None
    framework: str | None = None
    default_domain: str | None = None
    default_risk_class: str | None = None
    permissions: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class BlueprintOut(ORMModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    description: str | None
    connector_type: str
    framework: str
    default_domain: str | None
    default_risk_class: str
    permissions: dict[str, Any]
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class BlueprintRegisterRequest(BaseModel):
    """Create a registry agent from a blueprint (still needs identity + invoke_url)."""

    name: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1)
    invoke_url: str = Field(min_length=1)
    owner: str | None = None
    team: str | None = None
    domain: str | None = None
    environment: str = "dev"
    connection_id: UUID | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
