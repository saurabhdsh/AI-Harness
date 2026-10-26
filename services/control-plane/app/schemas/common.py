"""Shared schema primitives."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    detail: str


class ErrorOut(BaseModel):
    detail: str
    error_type: str | None = None
    operation: str | None = None
    connector_type: str | None = None


class PaginatedMeta(BaseModel):
    total: int
    limit: int
    offset: int


class Timestamped(ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime | None = None


class JSONDict(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
