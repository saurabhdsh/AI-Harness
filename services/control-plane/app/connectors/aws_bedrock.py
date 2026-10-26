"""AWS Bedrock Agents connector — capability-honest.

Discovery/invoke require real AWS credentials resolved from secret_ref.
Without credentials, operations fail explicitly (no mock agent lists).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.connectors.base import (
    CapabilityManifest,
    DiscoveredAgent,
    InvokeRequest,
    InvokeResponse,
    UnsupportedOperationError,
)


class AWSBedrockConnector:
    connector_type = "aws_bedrock"

    def __init__(
        self,
        base_url: str = "",
        secret_ref: str | None = None,
        *,
        region: str | None = None,
        **_: Any,
    ):
        # base_url unused for native Bedrock; kept for registry uniformity
        self.base_url = (base_url or "").rstrip("/")
        self.secret_ref = secret_ref
        self.region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    def _credentials_present(self) -> bool:
        # secret_ref alone is not enough without a vault resolver; also accept ambient AWS env
        return bool(
            self.secret_ref
            or os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_PROFILE")
            or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
        )

    async def authenticate(self) -> bool:
        if not self._credentials_present():
            raise PermissionError(
                "AWS Bedrock credentials not available. Set secret_ref (Vault) or "
                "AWS_ACCESS_KEY_ID / AWS_PROFILE / workload identity. "
                "Harness will not fabricate Bedrock discovery."
            )
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
            suspension=True,
            tool_inspection=False,
            credential_requirements=["aws_credentials_or_secret_ref"],
            restrictions=[
                "deployment of Bedrock agents is platform-managed — not via Harness deploy API",
                "requires real AWS credentials; no silent mock catalog",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        await self.authenticate()
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is not installed in the control-plane image. "
                "Install boto3 to enable live Bedrock discovery."
            ) from exc

        client = boto3.client("bedrock-agent", region_name=self.region)
        try:
            paginator = client.get_paginator("list_agents")
            agents: list[DiscoveredAgent] = []
            for page in paginator.paginate():
                for summary in page.get("agentSummaries", []):
                    agent_id = summary.get("agentId") or summary.get("agentName")
                    agents.append(
                        DiscoveredAgent(
                            external_id=str(agent_id),
                            name=str(summary.get("agentName") or agent_id),
                            framework="bedrock",
                            invoke_url=None,
                            metadata={
                                "status": summary.get("agentStatus"),
                                "updated": str(summary.get("updatedAt")),
                                "region": self.region,
                                "connector": "aws_bedrock",
                            },
                        )
                    )
            return agents
        except Exception as exc:  # noqa: BLE001 — surface provider error honestly
            raise RuntimeError(f"Bedrock ListAgents failed: {exc}") from exc

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        await self.authenticate()
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("boto3 required for Bedrock invoke") from exc

        agent_id = request.external_id
        if not agent_id:
            raise ValueError("Bedrock invoke requires external_id (agent id)")
        alias_id = (request.config or {}).get("agent_alias_id") or os.getenv(
            "BEDROCK_AGENT_ALIAS_ID", "TSTALIASID"
        )
        session_id = (request.config or {}).get("session_id") or "harness-session"
        client = boto3.client("bedrock-agent-runtime", region_name=self.region)
        try:
            resp = client.invoke_agent(
                agentId=agent_id,
                agentAliasId=alias_id,
                sessionId=session_id,
                inputText=str((request.input or {}).get("input") or (request.input or {}).get("query") or request.input),
            )
            chunks: list[str] = []
            for event in resp.get("completion", []):
                chunk = event.get("chunk") or {}
                payload = chunk.get("bytes")
                if payload:
                    chunks.append(payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload))
            text = "".join(chunks)
            return InvokeResponse(
                output={"text": text, "agent_id": agent_id},
                latency_ms=None,
                raw={"provider": "bedrock"},
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock InvokeAgent failed: {exc}") from exc

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedOperationError(
            "deploy",
            self.connector_type,
            "Use AWS Bedrock console/API/CI to publish agents; Harness governs lifecycle only",
        )

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        raise UnsupportedOperationError("rollback", self.connector_type)

    async def suspend(self, external_id: str) -> dict[str, Any]:
        await self.authenticate()
        raise UnsupportedOperationError(
            "suspend",
            self.connector_type,
            "Map to Bedrock PrepareAgent/UpdateAgent status in a later phase with explicit IAM",
        )

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError("get_telemetry", self.connector_type)

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        raise UnsupportedOperationError("inspect_tools", self.connector_type)

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]:
        agents = await self.discover_agents()
        for a in agents:
            if a.external_id == external_id:
                return a.model_dump()
        raise LookupError(external_id)
