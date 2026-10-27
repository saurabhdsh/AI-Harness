"""Skill Forge schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SkillCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=64)
    version: str = "1.0.0"
    description: str | None = None
    instructions: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    eval_suite: dict[str, Any] = Field(default_factory=dict)
    risk_class: str = "medium"
    tags: list[str] = Field(default_factory=list)
    sample_input: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    instructions: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    eval_suite: dict[str, Any] | None = None
    risk_class: str | None = None
    tags: list[str] | None = None
    sample_input: dict[str, Any] | None = None
    is_active: bool | None = None


class SkillOut(ORMModel):
    id: UUID
    tenant_id: UUID
    slug: str
    name: str
    domain: str
    version: str
    description: str | None
    instructions: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    eval_suite: dict[str, Any]
    risk_class: str
    tags: list[Any]
    sample_input: dict[str, Any]
    is_active: bool
    is_builtin: bool
    created_at: datetime
    updated_at: datetime


class AgentSkillAttach(BaseModel):
    skill_id: UUID
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class AgentSkillOut(ORMModel):
    id: UUID
    tenant_id: UUID
    agent_id: UUID
    skill_id: UUID
    config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    skill: SkillOut | None = None


class SkillSeedResult(BaseModel):
    created: int
    total: int
