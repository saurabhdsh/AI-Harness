"""Generic REST connector — real HTTP discovery and invocation."""

from __future__ import annotations

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


class GenericRESTConnector:
    """HTTP connector for agents exposing REST invoke (+ optional OpenAPI /agents)."""

    connector_type = "generic_rest"

    def __init__(
        self,
        base_url: str,
        secret_ref: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.secret_ref = secret_ref
        self._headers = dict(headers or {})
        self._timeout = timeout or get_settings().http_timeout_seconds
        if secret_ref:
            # Resolve secret_ref in production via a vault; for demo we treat it as bearer token ref name
            self._headers.setdefault("X-Secret-Ref", secret_ref)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=self._timeout,
        )

    async def authenticate(self) -> bool:
        async with self._client() as client:
            for path in ("/health", "/ready", "/"):
                try:
                    resp = await client.get(path)
                    if resp.status_code < 500:
                        return True
                except httpx.HTTPError:
                    continue
        raise ConnectionError(
            f"Failed to authenticate/reach connector at {self.base_url}"
        )

    async def get_capabilities(self) -> CapabilityManifest:
        return CapabilityManifest(
            discovery=True,
            metadata=True,
            invocation=True,
            telemetry=False,
            evaluation=False,
            deployment=False,
            rollback=False,
            suspension=False,
            tool_inspection=False,
            credential_requirements=["secret_ref"] if self.secret_ref else [],
            restrictions=[
                "deployment not supported",
                "rollback not supported",
                "suspension not supported",
                "telemetry not supported via this connector",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        async with self._client() as client:
            # Prefer /agents list
            try:
                resp = await client.get("/agents")
                if resp.status_code == 200:
                    data = resp.json()
                    agents_raw = data if isinstance(data, list) else data.get("agents", [])
                    return [self._map_discovered(a) for a in agents_raw]
            except httpx.HTTPError:
                pass

            # Fallback: OpenAPI paths that look like invoke endpoints
            try:
                resp = await client.get("/openapi.json")
                if resp.status_code == 200:
                    spec = resp.json()
                    paths = spec.get("paths", {})
                    discovered: list[DiscoveredAgent] = []
                    for path, methods in paths.items():
                        if "post" in methods and any(
                            k in path.lower() for k in ("invoke", "run", "predict", "chat")
                        ):
                            discovered.append(
                                DiscoveredAgent(
                                    external_id=path.strip("/").replace("/", "_") or "default",
                                    name=methods["post"].get("summary") or path,
                                    framework="rest",
                                    invoke_url=urljoin(self.base_url, path.lstrip("/")),
                                    metadata={"openapi_path": path},
                                )
                            )
                    if discovered:
                        return discovered
            except httpx.HTTPError:
                pass

        # Last resort: treat base URL itself as a single invokable agent
        return [
            DiscoveredAgent(
                external_id="default",
                name="rest-agent",
                framework="rest",
                invoke_url=urljoin(self.base_url, "invoke"),
                metadata={"source": "base_url_fallback"},
            )
        ]

    def _map_discovered(self, raw: dict[str, Any]) -> DiscoveredAgent:
        ext_id = str(raw.get("id") or raw.get("external_id") or raw.get("name") or "unknown")
        invoke = raw.get("invoke_url") or raw.get("url")
        if invoke and not str(invoke).startswith("http"):
            invoke = urljoin(self.base_url, str(invoke).lstrip("/"))
        return DiscoveredAgent(
            external_id=ext_id,
            name=str(raw.get("name") or ext_id),
            framework=raw.get("framework") or "rest",
            invoke_url=invoke,
            metadata={k: v for k, v in raw.items() if k not in {"id", "name", "invoke_url", "url"}},
        )

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]:
        async with self._client() as client:
            for path in (f"/agents/{external_id}", f"/agents/{external_id}/metadata"):
                try:
                    resp = await client.get(path)
                    if resp.status_code == 200:
                        return resp.json()
                except httpx.HTTPError:
                    continue
        agents = await self.discover_agents()
        for agent in agents:
            if agent.external_id == external_id:
                return agent.model_dump()
        raise LookupError(f"Agent '{external_id}' not found at {self.base_url}")

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        url = request.invoke_url
        if not url:
            url = urljoin(self.base_url, "invoke")
        elif not url.startswith("http"):
            url = urljoin(self.base_url, url.lstrip("/"))

        payload = {
            "input": request.input,
            "config": request.config,
        }
        if request.external_id:
            payload["agent_id"] = request.external_id

        started = time.perf_counter()
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            try:
                resp = await client.post(url, json=payload)
            except httpx.HTTPError as exc:
                raise ConnectionError(f"Agent invoke failed at {url}: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Agent invoke returned HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"Agent invoke returned non-JSON body: {resp.text[:200]}") from exc

        output = body.get("output", body.get("result", body))
        if not isinstance(output, dict):
            output = {"value": output}

        usage = body.get("usage") or body.get("tokens") or {}
        return InvokeResponse(
            output=output,
            latency_ms=latency_ms,
            token_input=usage.get("input") or usage.get("prompt_tokens"),
            token_output=usage.get("output") or usage.get("completion_tokens"),
            trace_id=body.get("trace_id") or body.get("run_id"),
            raw=body if isinstance(body, dict) else {"body": body},
        )

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        # No native platform metrics — Activity UI uses KEEL invoke rollups.
        return {
            "sessions": 0,
            "exceptions": 0,
            "runtime_seconds": 0,
            "unique_users": 0,
            "tool_calls": 0,
            "invocations": 0,
            "daily": [],
            "provider": self.connector_type,
            "available": False,
            "notes": ["Platform does not expose federated telemetry; KEEL invoke activity still applies."],
        }

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedOperationError("deploy", self.connector_type)

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        raise UnsupportedOperationError("rollback", self.connector_type)

    async def suspend(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError("suspend", self.connector_type)

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        raise UnsupportedOperationError("inspect_tools", self.connector_type)
