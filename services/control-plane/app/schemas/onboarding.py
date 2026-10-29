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
    source: str = Field(description="path | upload | cloud | ci | catalog")
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
    # Git / CI provenance (enterprise path)
    git_repo: str | None = None
    git_ref: str | None = None
    git_sha: str | None = None
    invoke_url: str | None = None


class CiRegisterRequest(BaseModel):
    """Post-deploy registration from CI/CD — upsert by external_id."""

    name: str = Field(min_length=1)
    external_id: str = Field(min_length=1, description="Stable agent id across deploys")
    invoke_url: str = Field(min_length=1, description="Fully qualified invoke URL after deploy")
    connector_type: str = "generic_rest"
    framework: str = "rest"
    base_url: str | None = None
    secret_ref: str | None = None
    domain: str | None = None
    environment: str = "dev"
    owner: str | None = None
    team: str | None = None
    description: str | None = None
    connection_name: str | None = None
    create_connection: bool = True
    # Git provenance
    git_repo: str | None = Field(default=None, description="https://github.com/org/repo")
    git_ref: str | None = None
    git_sha: str | None = None
    git_commit_url: str | None = None
    pipeline_id: str | None = None
    pipeline_url: str | None = None
    blueprint_id: UUID | None = None
    blueprint_slug: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CiRegisterResult(BaseModel):
    agent_id: UUID
    connection_id: UUID | None = None
    blueprint_id: UUID | None = None
    created: bool
    external_id: str
    invoke_url: str
    status: str = "registered"


class CatalogAgentEntry(BaseModel):
    name: str
    external_id: str
    invoke_url: str | None = None
    framework: str | None = None
    domain: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CatalogSyncRequest(BaseModel):
    """Sync a post-deploy catalog: discover from base_url and/or explicit agent list."""

    name: str = Field(min_length=1, description="Catalog / connection display name")
    connector_type: str = "generic_rest"
    base_url: str = Field(min_length=1)
    secret_ref: str | None = None
    agents: list[CatalogAgentEntry] = Field(default_factory=list)
    discover: bool = True
    domain: str | None = None
    environment: str = "dev"
    owner: str | None = None
    team: str | None = None
    git_repo: str | None = None
    git_ref: str | None = None
    git_sha: str | None = None
    blueprint_id: UUID | None = None
    blueprint_slug: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CatalogSyncResult(BaseModel):
    connection_id: UUID
    discovered: list[dict[str, Any]]
    registered_agent_ids: list[UUID]
    updated_agent_ids: list[UUID]
    status: str
    error: str | None = None
