"""Connector / platform connection schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.schemas.common import ORMModel


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    connector_type: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    secret_ref: str | None = None
    collect_observability: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    secret_ref: str | None = None
    collect_observability: bool | None = None
    metadata: dict[str, Any] | None = None


class ConnectorOut(ORMModel):
    id: UUID
    tenant_id: UUID
    name: str
    connector_type: str
    base_url: str
    secret_ref: str | None
    capabilities: dict[str, Any]
    status: str
    last_error: str | None
    last_synced_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    synced_agent_count: int = 0
    collect_observability: bool = True
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ConnectorValidateResponse(BaseModel):
    ok: bool
    capabilities: dict[str, Any]
    discovered_count: int | None = None
    error: str | None = None


class ConnectorSyncResult(BaseModel):
    connection_id: UUID
    discovered: list[dict[str, Any]] = Field(default_factory=list)
    registered_agent_ids: list[UUID] = Field(default_factory=list)
    updated_agent_ids: list[UUID] = Field(default_factory=list)
    status: str
    error: str | None = None
