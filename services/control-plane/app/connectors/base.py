"""Connector protocol, capability manifest, and typed unsupported errors."""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class UnsupportedOperationError(Exception):
    """Raised when a connector does not support the requested operation.

    Callers must surface this explicitly — never silently mock success.
    """

    def __init__(self, operation: str, connector_type: str, message: str | None = None):
        self.operation = operation
        self.connector_type = connector_type
        detail = message or f"Operation '{operation}' is not supported by connector '{connector_type}'"
        super().__init__(detail)


class CapabilityManifest(BaseModel):
    discovery: bool = False
    metadata: bool = False
    invocation: bool = False
    telemetry: bool = False
    evaluation: bool = False
    deployment: bool = False
    rollback: bool = False
    suspension: bool = False
    resume: bool = False
    restart: bool = False
    delete_source: bool = False
    tool_inspection: bool = False
    credential_requirements: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)


class DiscoveredAgent(BaseModel):
    external_id: str
    name: str
    framework: str | None = None
    invoke_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvokeRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    external_id: str | None = None
    invoke_url: str | None = None


class InvokeResponse(BaseModel):
    output: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None
    token_input: int | None = None
    token_output: int | None = None
    trace_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class AgentConnector(Protocol):
    connector_type: str

    async def authenticate(self) -> bool: ...

    async def discover_agents(self) -> list[DiscoveredAgent]: ...

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]: ...

    async def get_capabilities(self) -> CapabilityManifest: ...

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse: ...

    async def get_telemetry(self, external_id: str) -> dict[str, Any]: ...

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]: ...

    async def suspend(self, external_id: str) -> dict[str, Any]: ...

    async def resume(self, external_id: str) -> dict[str, Any]: ...

    async def restart(self, external_id: str) -> dict[str, Any]: ...

    async def delete_from_source(self, external_id: str) -> dict[str, Any]: ...

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]: ...
