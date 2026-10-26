"""ServiceNow AI Agent connector — capability-honest native control surface.

Targets agents built/hosted in ServiceNow (AI Agent Studio / Now Assist / scripted
agent façades), not generic agents that merely *call* ServiceNow as a tool.

Requires instance URL + credentials. Never fabricates agent catalogs or invoke success.
Deep Control Tower parity (policy packs, multi-instance CMDB sync) is phased —
discover + invoke + metadata ship first.
"""

from __future__ import annotations

import base64
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


class ServiceNowConnector:
    connector_type = "servicenow"

    def __init__(
        self,
        base_url: str,
        secret_ref: str | None = None,
        **_: Any,
    ):
        self.base_url = (base_url or os.getenv("SERVICENOW_INSTANCE_URL") or "").rstrip("/") + "/"
        self.secret_ref = secret_ref
        self._timeout = get_settings().http_timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        token = os.getenv("SERVICENOW_TOKEN") or os.getenv("SN_TOKEN")
        user = os.getenv("SERVICENOW_USER") or os.getenv("SN_USER")
        password = os.getenv("SERVICENOW_PASSWORD") or os.getenv("SN_PASSWORD")
        if self.secret_ref and ":" in self.secret_ref and not token and not user:
            # Demo vault convention: secret_ref = "basic:user:pass" or "bearer:<token>"
            kind, _, rest = self.secret_ref.partition(":")
            if kind == "bearer":
                token = rest
            elif kind == "basic":
                user, _, password = rest.partition(":")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif user and password:
            raw = base64.b64encode(f"{user}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {raw}"
        elif self.secret_ref:
            headers["X-Secret-Ref"] = self.secret_ref
        return headers

    def _ready(self) -> None:
        if not self.base_url.startswith("http"):
            raise ValueError(
                "ServiceNow instance URL required (e.g. https://<instance>.service-now.com)"
            )
        headers = self._headers()
        if "Authorization" not in headers and "X-Secret-Ref" not in headers:
            raise PermissionError(
                "ServiceNow credentials missing. Provide secret_ref "
                "(bearer:<token> | basic:user:pass | vault:…) or SERVICENOW_TOKEN / "
                "SERVICENOW_USER+SERVICENOW_PASSWORD. Harness will not invent SN agents."
            )

    async def authenticate(self) -> bool:
        self._ready()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            # Lightweight probe — Table API is universally present
            resp = await client.get("/api/now/table/sys_user", params={"sysparm_limit": 1})
            if resp.status_code in {401, 403}:
                raise PermissionError(
                    f"ServiceNow authentication failed ({resp.status_code}). "
                    "Check instance URL and credentials."
                )
            if resp.status_code >= 500:
                raise ConnectionError(f"ServiceNow unreachable: HTTP {resp.status_code}")
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
            tool_inspection=True,
            credential_requirements=["servicenow_instance_url", "servicenow_credential_or_secret_ref"],
            restrictions=[
                "Does not replace ServiceNow AI Control Tower — federates SN-hosted agents into Harness",
                "Full Control Tower policy/CMDB depth is roadmap; discover+invoke+lifecycle stubs first",
                "AI Agent Studio table names vary by SN family release — probes multiple tables",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        await self.authenticate()
        agents: list[DiscoveredAgent] = []
        # Probe known / likely AI agent tables across SN releases
        tables = [
            ("sn_aia_agent", "name"),
            ("sn_aia_agent_config", "name"),
            ("sys_hub_flow", "name"),
        ]
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            for table, name_field in tables:
                try:
                    resp = await client.get(
                        f"/api/now/table/{table}",
                        params={
                            "sysparm_limit": 50,
                            "sysparm_fields": f"sys_id,{name_field},active,description",
                        },
                    )
                except httpx.HTTPError as exc:
                    raise ConnectionError(f"ServiceNow discovery failed: {exc}") from exc
                if resp.status_code == 404:
                    continue
                if resp.status_code >= 400:
                    # Table may be ACL-restricted — try next
                    continue
                rows = (resp.json() or {}).get("result") or []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    sys_id = str(row.get("sys_id") or "")
                    if not sys_id:
                        continue
                    name = str(row.get(name_field) or row.get("name") or sys_id)
                    agents.append(
                        DiscoveredAgent(
                            external_id=sys_id,
                            name=name,
                            framework="servicenow",
                            invoke_url=urljoin(
                                self.base_url, f"api/sn_aia/v1/agent/{sys_id}/execute"
                            ),
                            metadata={
                                "connector": "servicenow",
                                "table": table,
                                "active": row.get("active"),
                                "instance": self.base_url.rstrip("/"),
                            },
                        )
                    )
                if agents:
                    break

        if not agents:
            raise RuntimeError(
                "No ServiceNow AI agents discovered. Ensure AI Agent Studio tables are "
                "licensed/visible to this user, or expose the agent via Scripted REST and "
                "onboard with generic_rest. Harness will not fabricate an SN catalog."
            )
        return agents

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        await self.authenticate()
        agent_id = request.external_id
        if not agent_id:
            raise ValueError("ServiceNow invoke requires external_id (sys_id)")

        candidates: list[str] = []
        if request.invoke_url:
            candidates.append(request.invoke_url)
        candidates.extend(
            [
                urljoin(self.base_url, f"api/sn_aia/v1/agent/{agent_id}/execute"),
                urljoin(self.base_url, f"api/sn_aia/agent/{agent_id}/run"),
                urljoin(self.base_url, "api/sn_va_as_service/bot/integration"),
            ]
        )

        payload = {
            "agent": agent_id,
            "inputs": request.input,
            "message": request.input.get("message")
            or request.input.get("task")
            or request.input.get("query"),
            "context": request.config or {},
        }

        errors: list[str] = []
        async with httpx.AsyncClient(headers=self._headers(), timeout=self._timeout) as client:
            for url in candidates:
                started = time.perf_counter()
                try:
                    resp = await client.post(url, json=payload)
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
                output = body.get("output") or body.get("result") or body.get("response") or body
                if not isinstance(output, dict):
                    output = {"value": output}
                return InvokeResponse(
                    output=output,
                    latency_ms=latency_ms,
                    trace_id=str(body.get("sys_id") or body.get("execution_id") or ""),
                    raw=body if isinstance(body, dict) else {"body": body},
                )

        raise RuntimeError(
            "ServiceNow agent invoke failed on all known endpoints. "
            f"Tried: {', '.join(candidates)}. Errors: {' | '.join(errors)}. "
            "Confirm AI Agent execute API is enabled for this instance, or publish a "
            "Scripted REST façade and set invoke_url."
        )

    async def suspend(self, external_id: str) -> dict[str, Any]:
        await self.authenticate()
        # Soft-disable via table update when possible
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            for table in ("sn_aia_agent", "sn_aia_agent_config"):
                resp = await client.patch(
                    f"/api/now/table/{table}/{external_id}",
                    json={"active": "false"},
                )
                if resp.status_code < 400:
                    return {"status": "suspended", "external_id": external_id, "table": table}
        raise UnsupportedOperationError(
            "suspend",
            self.connector_type,
            "Could not deactivate agent record — ACL or table unavailable",
        )

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        await self.authenticate()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            resp = await client.get(
                "/api/now/table/sn_aia_tool",
                params={
                    "sysparm_query": f"agent={external_id}",
                    "sysparm_limit": 50,
                    "sysparm_fields": "sys_id,name,type",
                },
            )
            if resp.status_code >= 400:
                raise UnsupportedOperationError(
                    "inspect_tools",
                    self.connector_type,
                    f"Tool table unavailable (HTTP {resp.status_code})",
                )
            rows = (resp.json() or {}).get("result") or []
            return [
                {
                    "id": r.get("sys_id"),
                    "name": r.get("name"),
                    "type": r.get("type"),
                }
                for r in rows
                if isinstance(r, dict)
            ]

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]:
        for a in await self.discover_agents():
            if a.external_id == external_id:
                return a.model_dump()
        raise LookupError(external_id)

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError(
            "get_telemetry",
            self.connector_type,
            "Native SN Analytics / Control Tower telemetry federation is roadmap",
        )

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedOperationError(
            "deploy",
            self.connector_type,
            "Deploy via ServiceNow Update Sets / App Repo — not claimed by Harness",
        )

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        raise UnsupportedOperationError("rollback", self.connector_type)
