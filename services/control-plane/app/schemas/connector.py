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
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ConnectorValidateResponse(BaseModel):
    ok: bool
    capabilities: dict[str, Any]
    discovered_count: int | None = None
    error: str | None = None
