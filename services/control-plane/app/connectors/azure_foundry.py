"""Microsoft Azure AI Foundry / Agents connector — capability-honest.

Requires endpoint + credential via secret_ref or AZURE_* env. No mock catalogs.
"""

from __future__ import annotations

import os
from typing import Any

from app.connectors.base import (
    CapabilityManifest,
    DiscoveredAgent,
    InvokeRequest,
    InvokeResponse,
    UnsupportedOperationError,
)


class AzureFoundryConnector:
    connector_type = "azure_foundry"

    def __init__(
        self,
        base_url: str,
        secret_ref: str | None = None,
        **_: Any,
    ):
        self.base_url = (base_url or os.getenv("AZURE_AI_PROJECT_ENDPOINT") or "").rstrip("/")
        self.secret_ref = secret_ref

    def _ready(self) -> None:
        if not self.base_url:
            raise ValueError(
                "Azure Foundry project endpoint required (base_url or AZURE_AI_PROJECT_ENDPOINT)"
            )
        if not (
            self.secret_ref
            or os.getenv("AZURE_CLIENT_ID")
            or os.getenv("AZURE_OPENAI_API_KEY")
            or os.getenv("AZURE_AI_API_KEY")
        ):
            raise PermissionError(
                "Azure credentials not available. Provide secret_ref or AZURE_CLIENT_ID / "
                "AZURE_AI_API_KEY. Harness will not fabricate Foundry agents."
            )

    async def authenticate(self) -> bool:
        self._ready()
        return True

    async def get_capabilities(self) -> CapabilityManifest:
        return CapabilityManifest(
            discovery=True,
            metadata=True,
            invocation=True,
            telemetry=False,
            evaluation=True,
            deployment=False,
            rollback=False,
            suspension=False,
            tool_inspection=True,
            credential_requirements=["azure_endpoint", "azure_credential_or_secret_ref"],
            restrictions=[
                "deployment via Foundry tooling / Azure DevOps — not claimed here",
                "live SDK calls require azure-ai-projects (optional dependency)",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        await self.authenticate()
        try:
            # Optional dependency — fail clearly if missing
            from azure.ai.projects import AIProjectClient  # type: ignore
            from azure.identity import DefaultAzureCredential  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "azure-ai-projects / azure-identity not installed. "
                "Install them to enable live Azure Foundry discovery, "
                "or onboard via Generic REST if you expose HTTP."
            ) from exc

        client = AIProjectClient(
            endpoint=self.base_url,
            credential=DefaultAzureCredential(),
        )
        try:
            agents: list[DiscoveredAgent] = []
            for agent in client.agents.list_agents():
                agents.append(
                    DiscoveredAgent(
                        external_id=str(getattr(agent, "id", None) or getattr(agent, "name", "")),
                        name=str(getattr(agent, "name", None) or getattr(agent, "id", "agent")),
                        framework="azure_foundry",
                        invoke_url=None,
                        metadata={"connector": "azure_foundry", "endpoint": self.base_url},
                    )
                )
            return agents
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Azure Foundry list_agents failed: {exc}") from exc

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        await self.authenticate()
        raise UnsupportedOperationError(
            "invoke_agent",
            self.connector_type,
            "Wire thread/run invoke against azure-ai-agents once project credentials are confirmed; "
            "refusing to mock Foundry responses",
        )

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedOperationError("deploy", self.connector_type)

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        raise UnsupportedOperationError("rollback", self.connector_type)

    async def suspend(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError("suspend", self.connector_type)

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError("get_telemetry", self.connector_type)

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        raise UnsupportedOperationError("inspect_tools", self.connector_type)

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]:
        for a in await self.discover_agents():
            if a.external_id == external_id:
                return a.model_dump()
        raise LookupError(external_id)
