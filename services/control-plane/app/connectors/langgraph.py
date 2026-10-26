"""LangGraph-style agent connector — real HTTP invoke to /invoke or /runs."""

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
from app.connectors.generic_rest import GenericRESTConnector
from app.core.config import get_settings


class LangGraphConnector(GenericRESTConnector):
    """Wraps REST invoke for LangGraph agents (/invoke or /runs)."""

    connector_type = "langgraph"

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
                "deployment not supported via LangGraph connector",
                "rollback not supported",
                "suspension not supported",
                "tool inspection not available",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        # Try parent discovery first; if only fallback, label as langgraph
        agents = await super().discover_agents()
        for agent in agents:
            agent.framework = agent.framework or "langgraph"
            if not agent.invoke_url:
                agent.invoke_url = urljoin(self.base_url, "invoke")
            agent.metadata.setdefault("connector", "langgraph")
        return agents

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        """Try agent invoke_url, then /invoke, then /runs — never invent success.

        `/runs/wait` is LangGraph Platform-only and is intentionally not probed;
        a 404 there previously masked real connection failures to /invoke.
        """
        candidates: list[str] = []
        if request.invoke_url:
            candidates.append(request.invoke_url)
        candidates.extend(
            [
                urljoin(self.base_url, "invoke"),
                urljoin(self.base_url, "runs"),
            ]
        )

        # Deduplicate while preserving order
        seen: set[str] = set()
        urls: list[str] = []
        for u in candidates:
            if not u.startswith("http"):
                u = urljoin(self.base_url, u.lstrip("/"))
            if u not in seen:
                seen.add(u)
                urls.append(u)

        payload = self._build_payload(request)
        errors: list[str] = []
        timeout = self._timeout or get_settings().http_timeout_seconds

        async with httpx.AsyncClient(headers=self._headers, timeout=timeout) as client:
            for url in urls:
                started = time.perf_counter()
                try:
                    resp = await client.post(url, json=payload)
                except httpx.HTTPError as exc:
                    errors.append(f"{url} → connection error: {exc}")
                    # If the primary invoke_url cannot be reached, fail fast with
                    # a clear host-unreachable message instead of cascading 404s.
                    if request.invoke_url and url.rstrip("/") == str(request.invoke_url).rstrip("/"):
                        raise ConnectionError(
                            f"LangGraph agent unreachable at {url}. "
                            f"Is the agent process running? Underlying error: {exc}"
                        ) from exc
                    continue

                latency_ms = (time.perf_counter() - started) * 1000
                if resp.status_code == 404:
                    errors.append(f"{url} → HTTP 404")
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"LangGraph invoke HTTP {resp.status_code} at {url}: {resp.text[:500]}"
                    )

                try:
                    body = resp.json()
                except ValueError as exc:
                    raise RuntimeError(
                        f"LangGraph invoke non-JSON at {url}: {resp.text[:200]}"
                    ) from exc

                return self._parse_response(body, latency_ms)

        raise ConnectionError(
            f"All LangGraph invoke endpoints failed for {self.base_url}. "
            f"Tried: {', '.join(urls)}. Errors: {' | '.join(errors) or 'unknown'}"
        )

    def _build_payload(self, request: InvokeRequest) -> dict[str, Any]:
        # LangGraph common shapes: {"input": {...}} or {"input": {...}, "config": {...}}
        payload: dict[str, Any] = {"input": request.input}
        if request.config:
            payload["config"] = request.config
        return payload

    def _parse_response(self, body: Any, latency_ms: float) -> InvokeResponse:
        if not isinstance(body, dict):
            return InvokeResponse(
                output={"value": body},
                latency_ms=latency_ms,
                raw={"body": body},
            )

        output = body.get("output")
        if output is None:
            output = body.get("result") or body.get("values") or body
        if not isinstance(output, dict):
            output = {"value": output}
        else:
            # Preserve DAG / message evidence for evaluation without losing structured output
            enriched = dict(output)
            meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
            if "nodes" not in enriched and meta.get("nodes"):
                enriched["nodes"] = meta["nodes"]
            if "messages" not in enriched and isinstance(body.get("messages"), list):
                enriched["messages"] = body["messages"]
            if meta.get("latency_ms") is not None and "latency_ms" not in enriched:
                enriched["latency_ms"] = meta["latency_ms"]
            output = enriched

        usage = body.get("usage") or {}
        return InvokeResponse(
            output=output,
            latency_ms=latency_ms,
            token_input=usage.get("input_tokens") or usage.get("prompt_tokens"),
            token_output=usage.get("output_tokens") or usage.get("completion_tokens"),
            trace_id=body.get("run_id") or body.get("trace_id") or body.get("thread_id"),
            raw=body,
        )

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedOperationError(
            "deploy",
            self.connector_type,
            "LangGraph connector does not support remote deployment",
        )

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        raise UnsupportedOperationError("rollback", self.connector_type)

    async def suspend(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError("suspend", self.connector_type)

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        raise UnsupportedOperationError("get_telemetry", self.connector_type)

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        raise UnsupportedOperationError("inspect_tools", self.connector_type)
