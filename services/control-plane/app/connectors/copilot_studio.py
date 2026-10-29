"""Microsoft Copilot Studio connector — capability-honest.

Discovers Copilot Studio agents (bots) from a Power Platform / Dataverse environment.
Requires environment URL + bearer token (or ambient COPILOT_STUDIO_* / DATAVERSE_* env).
Does not fabricate catalogs or mock Direct Line invokes.
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
from app.core.config import get_settings


class CopilotStudioConnector:
    """Connected-platform connector for Microsoft Copilot Studio agents."""

    connector_type = "copilot_studio"

    def __init__(
        self,
        base_url: str,
        secret_ref: str | None = None,
        **_: Any,
    ):
        env = (
            base_url
            or os.getenv("COPILOT_STUDIO_ENVIRONMENT_URL")
            or os.getenv("DATAVERSE_URL")
            or os.getenv("POWER_PLATFORM_ENV_URL")
            or ""
        )
        self.base_url = env.rstrip("/") + ("/" if env else "")
        self.secret_ref = secret_ref
        self._timeout = get_settings().http_timeout_seconds

    def _token(self) -> str | None:
        token = (
            os.getenv("COPILOT_STUDIO_TOKEN")
            or os.getenv("DATAVERSE_TOKEN")
            or os.getenv("POWER_PLATFORM_TOKEN")
        )
        if self.secret_ref:
            kind, _, rest = self.secret_ref.partition(":")
            if kind == "bearer" and rest:
                token = rest
            elif kind == "vault" and not token:
                # Opaque vault ref — surface as missing until vault resolver exists
                return None
            elif not kind.startswith("vault") and ":" not in self.secret_ref and self.secret_ref:
                # Bare token in secret_ref
                token = self.secret_ref
        return token or None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        token = self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.secret_ref:
            headers["X-Secret-Ref"] = self.secret_ref
        return headers

    def _ready(self) -> None:
        if not self.base_url.startswith("http"):
            raise ValueError(
                "Copilot Studio environment URL required "
                "(e.g. https://org.crm.dynamics.com or https://xxxx.api.crm.dynamics.com)"
            )
        if "Authorization" not in self._headers() and "X-Secret-Ref" not in self._headers():
            raise PermissionError(
                "Copilot Studio credentials missing. Provide secret_ref as bearer:<token> "
                "or set COPILOT_STUDIO_TOKEN / DATAVERSE_TOKEN. "
                "Harness will not invent Copilot Studio agents."
            )

    async def authenticate(self) -> bool:
        self._ready()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            # WhoAmI is a light Dataverse probe
            resp = await client.get("api/data/v9.2/WhoAmI")
            if resp.status_code in {401, 403}:
                raise PermissionError(
                    f"Copilot Studio / Dataverse authentication failed ({resp.status_code}). "
                    "Check environment URL and bearer token (Dataverse scope)."
                )
            if resp.status_code >= 500:
                raise ConnectionError(
                    f"Dataverse environment unreachable: HTTP {resp.status_code}"
                )
            # 404 may mean wrong host shape — still try discovery
            return True

    async def get_capabilities(self) -> CapabilityManifest:
        return CapabilityManifest(
            discovery=True,
            metadata=True,
            invocation=False,
            telemetry=True,
            evaluation=False,
            deployment=True,
            rollback=False,
            suspension=True,
            resume=True,
            restart=True,
            delete_source=True,
            tool_inspection=False,
            credential_requirements=[
                "power_platform_environment_url",
                "dataverse_bearer_or_secret_ref",
            ],
            restrictions=[
                "Direct Line / Bot Framework invoke not claimed here — register invoke_url via CI if needed",
                "Requires Dataverse write privilege on bots for lifecycle",
                "rollback of Copilot Studio content versions is not exposed via Dataverse bots API",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        await self.authenticate()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            # Copilot Studio agents are stored as Dataverse "bots"
            resp = await client.get(
                "api/data/v9.2/bots",
                params={
                    "$select": "botid,name,schemaname,statecode,statuscode",
                    "$filter": "statecode eq 0",
                },
            )
            if resp.status_code in {401, 403}:
                raise PermissionError(
                    f"Dataverse bots list denied ({resp.status_code}). "
                    "Token needs privileges to read Copilot Studio bots."
                )
            if resp.status_code == 404:
                # Fallback: unfiltered (older orgs)
                resp = await client.get(
                    "api/data/v9.2/bots",
                    params={"$select": "botid,name,schemaname"},
                )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Copilot Studio discovery failed: HTTP {resp.status_code} {resp.text[:300]}"
                )

            payload = resp.json()
            rows = payload.get("value") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                rows = []

            agents: list[DiscoveredAgent] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                bot_id = str(row.get("botid") or row.get("botId") or "")
                name = str(row.get("name") or row.get("schemaname") or bot_id or "copilot-bot")
                if not bot_id:
                    continue
                agents.append(
                    DiscoveredAgent(
                        external_id=bot_id,
                        name=name,
                        framework="copilot_studio",
                        invoke_url=None,
                        metadata={
                            "connector": "copilot_studio",
                            "schemaname": row.get("schemaname"),
                            "environment": self.base_url.rstrip("/"),
                            "statecode": row.get("statecode"),
                        },
                    )
                )
            return agents

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]:
        for a in await self.discover_agents():
            if a.external_id == external_id:
                return a.model_dump()
        raise LookupError(external_id)

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        await self.authenticate()
        raise UnsupportedOperationError(
            "invoke_agent",
            self.connector_type,
            "Copilot Studio invoke uses Direct Line / Bot Framework channels. "
            "Sync registers inventory only; set a published invoke_url via CI register to execute.",
        )

    async def _patch_bot_state(self, external_id: str, statecode: int) -> dict[str, Any]:
        await self.authenticate()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            resp = await client.patch(
                f"api/data/v9.2/bots({external_id})",
                json={"statecode": statecode, "statuscode": 1 if statecode == 0 else 2},
            )
            if resp.status_code in {401, 403}:
                raise PermissionError(
                    f"Dataverse bot update denied ({resp.status_code}). "
                    "Token needs write privilege on bots."
                )
            if resp.status_code >= 400 and resp.status_code != 204:
                raise RuntimeError(
                    f"Copilot Studio state change failed: HTTP {resp.status_code} {resp.text[:300]}"
                )
            return {
                "provider": "copilot_studio",
                "bot_id": external_id,
                "statecode": statecode,
                "active": statecode == 0,
            }

    async def suspend(self, external_id: str) -> dict[str, Any]:
        """Deactivate Copilot Studio bot (statecode=1)."""
        result = await self._patch_bot_state(external_id, 1)
        result["operation"] = "suspend"
        return result

    async def resume(self, external_id: str) -> dict[str, Any]:
        """Activate Copilot Studio bot (statecode=0)."""
        result = await self._patch_bot_state(external_id, 0)
        result["operation"] = "resume"
        return result

    async def restart(self, external_id: str) -> dict[str, Any]:
        sus = await self.suspend(external_id)
        res = await self.resume(external_id)
        return {
            "provider": "copilot_studio",
            "operation": "restart",
            "bot_id": external_id,
            "suspend": sus,
            "resume": res,
        }

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Publish Copilot Studio bot content snapshot when Dataverse action exists."""
        await self.authenticate()
        bot_id = str(payload.get("external_id") or payload.get("agent_id") or "")
        if not bot_id:
            raise ValueError("deploy requires external_id (Copilot Studio bot id)")
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            # Try known PVA publish unbound/bound actions (orgs vary by API version)
            actions = [
                f"api/data/v9.2/bots({bot_id})/Microsoft.Dynamics.CRM.PvaPublish",
                f"api/data/v9.2/bots({bot_id})/Microsoft.Dynamics.CRM.PvaCreateContentSnapshot",
                f"api/data/v9.2/bots({bot_id})/Microsoft.Dynamics.CRM.PvaPublishBot",
            ]
            last_error = ""
            for path in actions:
                resp = await client.post(path, json={})
                if resp.status_code in {200, 201, 204}:
                    return {
                        "provider": "copilot_studio",
                        "operation": "deploy",
                        "bot_id": bot_id,
                        "action": path.rsplit(".", 1)[-1],
                        "http_status": resp.status_code,
                    }
                last_error = f"HTTP {resp.status_code} {resp.text[:200]}"
                if resp.status_code not in {404, 501, 400}:
                    break
            # Fallback: ensure bot is active (resume) as a minimal "go live"
            activated = await self.resume(bot_id)
            return {
                "provider": "copilot_studio",
                "operation": "deploy",
                "bot_id": bot_id,
                "action": "activate_fallback",
                "publish_error": last_error,
                "activated": activated,
            }

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        raise UnsupportedOperationError(
            "rollback",
            self.connector_type,
            "Copilot Studio content rollback is not available via Dataverse bots API; "
            "use Copilot Studio version history in the authoring canvas.",
        )

    async def delete_from_source(self, external_id: str) -> dict[str, Any]:
        await self.authenticate()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            resp = await client.delete(f"api/data/v9.2/bots({external_id})")
            if resp.status_code in {401, 403}:
                raise PermissionError(
                    f"Dataverse bot delete denied ({resp.status_code})."
                )
            if resp.status_code >= 400 and resp.status_code not in {204, 404}:
                raise RuntimeError(
                    f"Copilot Studio delete failed: HTTP {resp.status_code} {resp.text[:300]}"
                )
            return {
                "provider": "copilot_studio",
                "operation": "delete_from_source",
                "bot_id": external_id,
                "deleted": resp.status_code in {204, 200, 404},
                "http_status": resp.status_code,
            }

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        """Best-effort Copilot Studio activity — bot state + placeholder sessions.

        Power Platform analytics APIs vary by tenant; we surface state honestly and
        leave session metrics for KEEL invoke rollups / future PVA analytics hooks.
        """
        await self.authenticate()
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=self._timeout
        ) as client:
            resp = await client.get(
                f"api/data/v9.2/bots({external_id})",
                params={"$select": "botid,name,statecode,statuscode,modifiedon"},
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Copilot Studio telemetry read failed: HTTP {resp.status_code}"
                )
            bot = resp.json() if resp.content else {}
            active = int(bot.get("statecode") or 0) == 0
            return {
                "sessions": 0,
                "exceptions": 0 if active else 1,
                "runtime_seconds": 0,
                "unique_users": 0,
                "tool_calls": 0,
                "invocations": 0,
                "daily": [],
                "provider": "copilot_studio",
                "available": False,
                "bot_statecode": bot.get("statecode"),
                "bot_active": active,
                "notes": [
                    "Session/runtime metrics require Power Platform analytics; "
                    "KEEL Activity still includes control-plane invokes for this agent."
                ],
            }

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        raise UnsupportedOperationError("inspect_tools", self.connector_type)
