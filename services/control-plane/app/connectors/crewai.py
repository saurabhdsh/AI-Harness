"""CrewAI connector — HTTP invoke for CrewAI agents exposed over REST."""

from __future__ import annotations

from urllib.parse import urljoin

from app.connectors.base import CapabilityManifest, DiscoveredAgent, UnsupportedOperationError
from app.connectors.generic_rest import GenericRESTConnector


class CrewAIConnector(GenericRESTConnector):
    connector_type = "crewai"

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
            tool_inspection=False,
            credential_requirements=["secret_ref"] if self.secret_ref else [],
            restrictions=[
                "deployment not supported via CrewAI connector",
                "expects HTTP /agents + /invoke (or /kickoff) surface",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        agents = await super().discover_agents()
        for agent in agents:
            agent.framework = agent.framework or "crewai"
            if not agent.invoke_url:
                agent.invoke_url = urljoin(self.base_url, "invoke")
            agent.metadata.setdefault("connector", "crewai")
        return agents

    async def deploy(self, payload: dict) -> dict:
        raise UnsupportedOperationError("deploy", self.connector_type)

    async def rollback(self, external_id: str, version: str) -> dict:
        raise UnsupportedOperationError("rollback", self.connector_type)

    async def suspend(self, external_id: str) -> dict:
        raise UnsupportedOperationError("suspend", self.connector_type)
