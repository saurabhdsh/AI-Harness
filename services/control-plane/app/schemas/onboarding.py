"""Onboarding job schemas."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OnboardingJobCreate(BaseModel):
    name: str = Field(min_length=1)
    connector_type: str = "langgraph"
    base_url: str = ""
    secret_ref: str | None = None
    auto_register: bool = True
    owner: str | None = None
    team: str | None = None
    domain: str | None = None
    environment: str = "dev"
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Optional: external agent id for cloud platforms (Bedrock agent id, etc.)
    external_id: str | None = None
    # Project context from detection
    project_root: str | None = None
    detected_framework: str | None = None


class OnboardingJobResult(BaseModel):
    connection_id: UUID
    discovered: list[dict[str, Any]]
    registered_agent_ids: list[UUID]
    status: str
    error: str | None = None
    detection: dict[str, Any] | None = None


class PathDetectRequest(BaseModel):
    path: str = Field(min_length=1, description="Absolute path to agent project on the harness host")


class ProjectOnboardRequest(BaseModel):
    """Complete smart onboard after detection: connect + register."""

    name: str = Field(min_length=1)
    source: str = Field(description="path | upload | cloud")
    project_root: str | None = None
    upload_id: str | None = None
    connector_type: str | None = None
    base_url: str = ""
    secret_ref: str | None = None
    external_id: str | None = None
    auto_register: bool = True
    owner: str | None = None
    team: str | None = None
    domain: str | None = "ad"
    environment: str = "dev"
    metadata: dict[str, Any] = Field(default_factory=dict)
    run_invoke_smoke: bool = False
