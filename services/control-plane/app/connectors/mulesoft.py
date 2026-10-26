"""MuleSoft Agent Fabric / Anypoint connector — capability-honest.

Federates agents published on MuleSoft (Agent Fabric, Anypoint HTTP APIs, Exchange
agent assets) into the Harness control plane. Does not replace MuleSoft Agent Fabric
as a product — it is the cross-platform layer above it.

Requires Anypoint org credentials + optional Agent Fabric / API base URL.
Never fabricates discovery or invoke success.
"""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.connectors.base import (
    CapabilityManifest,
    DiscoveredAgent,
    InvokeRequest,
    InvokeResponse,
    UnsupportedOperationError,
)
from app.core.config import get_settings


class MuleSoftConnector:
    connector_type = "mulesoft"

    def __init__(
        self,
        base_url: str,
        secret_ref: str | None = None,
        **_: Any,
    ):
        # Agent / API runtime base (preferred for invoke). Auth host may differ.
        self.base_url = (
            base_url or os.getenv("MULESOFT_AGENT_BASE_URL") or os.getenv("MULESOFT_BASE_URL") or ""
        ).rstrip("/") + ("/" if (base_url or os.getenv("MULESOFT_AGENT_BASE_URL") or os.getenv("MULESOFT_BASE_URL")) else "")
        self.secret_ref = secret_ref
        self.anypoint_host = (
            os.getenv("ANYPOINT_BASE_URL") or "https://anypoint.mulesoft.com"
        ).rstrip("/")
        self._timeout = get_settings().http_timeout_seconds
        self._access_token: str | None = None

    def _client_creds(self) -> tuple[str | None, str | None]:
        client_id = os.getenv("ANYPOINT_CLIENT_ID") or os.getenv("MULESOFT_CLIENT_ID")
        client_secret = os.getenv("ANYPOINT_CLIENT_SECRET") or os.getenv("MULESOFT_CLIENT_SECRET")
        if self.secret_ref and self.secret_ref.startswith("oauth:"):
            # secret_ref = "oauth:client_id:client_secret"
            parts = self.secret_ref.split(":", 2)
            if len(parts) == 3:
                client_id, client_secret = parts[1], parts[2]
        return client_id, client_secret

    def _bearer_from_env(self) -> str | None:
        return os.getenv("ANYPOINT_TOKEN") or os.getenv("MULESOFT_TOKEN")

    async def _ensure_token(self) -> str:
        existing = self._bearer_from_env() or self._access_token
        if existing:
            return existing
        client_id, client_secret = self._client_creds()
        if not client_id or not client_secret:
            raise PermissionError(
                "MuleSoft / Anypoint credentials missing. Provide secret_ref "
                "oauth:<client_id>:<client_secret>, or ANYPOINT_CLIENT_ID + "
                "ANYPOINT_CLIENT_SECRET / ANYPOINT_TOKEN. Harness will not invent agents."
            )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self.anypoint_host}/accounts/api/v2/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code >= 400:
            raise PermissionError(
                f"Anypoint OAuth failed ({resp.status_code}): {resp.text[:300]}"
            )
        token = (resp.json() or {}).get("access_token")
        if not token:
            raise PermissionError("Anypoint OAuth response missing access_token")
        self._access_token = str(token)
        return self._access_token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def authenticate(self) -> bool:
        await self._ensure_token()
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
            tool_inspection=False,
            credential_requirements=[
                "anypoint_oauth_or_token",
                "optional_agent_runtime_base_url",
            ],
            restrictions=[
                "Does not replace MuleSoft Agent Fabric — federates Fabric/HTTP agents into Harness",
                "Deploy/promote stays in Anypoint; Harness owns cross-platform govern/eval/observe",
                "Agent Fabric catalog APIs evolve — Exchange + runtime HTTP probes used",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        token = await self._ensure_token()
        headers = self._auth_headers(token)
        agents: list[DiscoveredAgent] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # 1) Local runtime catalog if base_url points at an Agent Fabric / API gateway
            if self.base_url.startswith("http"):
                for path in ("/agents", "/api/agents", "/agent-fabric/agents"):
                    try:
                        resp = await client.get(urljoin(self.base_url, path.lstrip("/")), headers=headers)
                    except httpx.HTTPError:
                        continue
                    if resp.status_code >= 400:
                        continue
                    body = resp.json()
                    rows = body if isinstance(body, list) else (body.get("agents") or body.get("data") or [])
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        eid = str(row.get("id") or row.get("agentId") or row.get("name") or "")
                        if not eid:
                            continue
                        invoke = row.get("invoke_url") or row.get("endpoint") or row.get("url")
                        agents.append(
                            DiscoveredAgent(
                                external_id=eid,
                                name=str(row.get("name") or eid),
                                framework="mulesoft",
                                invoke_url=str(invoke) if invoke else urljoin(self.base_url, f"agents/{eid}/invoke"),
                                metadata={
                                    "connector": "mulesoft",
                                    "source": "runtime_catalog",
                                    "raw_keys": list(row.keys())[:12],
                                },
                            )
                        )
                    if agents:
                        return agents

            # 2) Anypoint Exchange search for agent-tagged assets
            org_id = os.getenv("ANYPOINT_ORG_ID") or os.getenv("MULESOFT_ORG_ID")
            exchange_url = f"{self.anypoint_host}/exchange/api/v2/assets"
            params: dict[str, Any] = {"search": "agent", "limit": 25}
            if org_id:
                params["organizationId"] = org_id
            resp = await client.get(exchange_url, headers=headers, params=params)
            if resp.status_code < 400:
                body = resp.json()
                rows = body if isinstance(body, list) else (body.get("assets") or body.get("data") or [])
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    eid = str(row.get("assetId") or row.get("id") or row.get("name") or "")
                    if not eid:
                        continue
                    name = str(row.get("name") or row.get("groupId") or eid)
                    # Prefer agent-like assets
                    labels = " ".join(
                        str(x)
                        for x in [
                            row.get("name"),
                            row.get("description"),
                            row.get("type"),
                            " ".join(row.get("categories") or []),
                        ]
                        if x
                    ).lower()
                    if "agent" not in labels and "fabric" not in labels:
                        continue
                    agents.append(
                        DiscoveredAgent(
                            external_id=eid,
                            name=name,
                            framework="mulesoft",
                            invoke_url=None,
                            metadata={
                                "connector": "mulesoft",
                                "source": "anypoint_exchange",
                                "groupId": row.get("groupId"),
                                "version": row.get("version"),
                            },
                        )
                    )

        if not agents:
            raise RuntimeError(
                "No MuleSoft agents discovered. Point base_url at an Agent Fabric / "
                "HTTP agent catalog, or ensure Anypoint Exchange has agent assets visible "
                "to this connected app. Harness will not fabricate a Fabric catalog."
            )
        return agents

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        token = await self._ensure_token()
        headers = self._auth_headers(token)

        candidates: list[str] = []
        if request.invoke_url:
            candidates.append(request.invoke_url)
        if self.base_url.startswith("http") and request.external_id:
            eid = request.external_id
            candidates.extend(
                [
                    urljoin(self.base_url, f"agents/{eid}/invoke"),
                    urljoin(self.base_url, f"api/agents/{eid}/invoke"),
                    urljoin(self.base_url, f"agent-fabric/agents/{eid}/run"),
                    urljoin(self.base_url, "invoke"),
                ]
            )
        if not candidates:
            raise ValueError(
                "MuleSoft invoke needs invoke_url or base_url + external_id "
                "(Agent Fabric runtime endpoint)"
            )

        payload = {
            "input": request.input,
            "agentId": request.external_id,
            "config": request.config or {},
        }
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for url in candidates:
                started = time.perf_counter()
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    errors.append(f"{url} → {exc}")
                    continue
                latency_ms = (time.perf_counter() - started) * 1000
                if resp.status_code == 404:
                    errors.append(f"{url} → HTTP 404")
                    continue
                if resp.status_code >= 400:
                    errors.append(f"{url} → HTTP {resp.status_code}: {resp.text[:200]}")
                    continue
                try:
                    body = resp.json()
                except ValueError:
                    body = {"raw": resp.text[:2000]}
                if not isinstance(body, dict):
                    body = {"value": body}
                output = body.get("output") or body.get("result") or body.get("payload") or body
                if not isinstance(output, dict):
                    output = {"value": output}
                return InvokeResponse(
                    output=output,
                    latency_ms=latency_ms,
                    trace_id=str(body.get("correlationId") or body.get("traceId") or ""),
                    raw=body if isinstance(body, dict) else {"body": body},
                )

        raise RuntimeError(
            "MuleSoft agent invoke failed on all candidates. "
            f"Errors: {' | '.join(errors)}. Confirm Agent Fabric runtime URL / API is published."
        )

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]:
        for a in await self.discover_agents():
            if a.external_id == external_id:
                return a.model_dump()
        raise LookupError(external_id)

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError(
            "get_telemetry",
            self.connector_type,
            "Anypoint Monitoring federation is roadmap",
        )

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedOperationError(
            "deploy",
            self.connector_type,
            "Deploy via Anypoint / Agent Fabric tooling — not claimed here",
        )

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        raise UnsupportedOperationError("rollback", self.connector_type)

    async def suspend(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError("suspend", self.connector_type)

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        raise UnsupportedOperationError("inspect_tools", self.connector_type)
