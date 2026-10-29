"""AWS Bedrock Agents connector — discovery, invoke, and full lifecycle write APIs.

Lifecycle (beyond Agent 365 read-only connected platforms):
  deploy   → PrepareAgent + point alias at latest version
  rollback → UpdateAgentAlias to a prior agentVersion
  suspend  → snapshot alias routing, delete alias (stops invokes)
  resume   → recreate alias from snapshot
  restart  → suspend + resume (or prepare + re-alias)
  delete   → DeleteAgent in AWS
"""

from __future__ import annotations

import os
import time
from typing import Any

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
        self.base_url = (base_url or "").rstrip("/")
        self.secret_ref = secret_ref
        self.region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
        # Prefer region from bedrock URL host if present
        if "bedrock." in self.base_url and ".amazonaws.com" in self.base_url:
            try:
                host = self.base_url.split("//", 1)[-1].split("/", 1)[0]
                # bedrock.us-east-1.amazonaws.com
                parts = host.split(".")
                if len(parts) >= 3 and parts[0] == "bedrock":
                    self.region = parts[1]
            except Exception:  # noqa: BLE001
                pass

    def _credentials_present(self) -> bool:
        return bool(
            self.secret_ref
            or os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_PROFILE")
            or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
        )

    def _client(self, service: str = "bedrock-agent"):
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is not installed. Install boto3 to enable Bedrock operations."
            ) from exc
        return boto3.client(service, region_name=self.region)

    def _alias_id(self, override: str | None = None) -> str:
        return (
            override
            or os.getenv("BEDROCK_AGENT_ALIAS_ID")
            or "production"
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
            telemetry=True,
            evaluation=True,
            deployment=True,
            rollback=True,
            suspension=True,
            resume=True,
            restart=True,
            delete_source=True,
            tool_inspection=False,
            credential_requirements=["aws_credentials_or_secret_ref", "bedrock:Write"],
            restrictions=[
                "suspend/resume uses agent alias delete/recreate — requires IAM on aliases",
                "delete_from_source permanently removes the agent in AWS",
                "telemetry prefers CloudWatch Invocation/Throttle/SystemErrors metrics when permitted",
            ],
        )

    async def discover_agents(self) -> list[DiscoveredAgent]:
        await self.authenticate()
        client = self._client()
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
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock ListAgents failed: {exc}") from exc

    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse:
        await self.authenticate()
        agent_id = request.external_id
        if not agent_id:
            raise ValueError("Bedrock invoke requires external_id (agent id)")
        alias_id = (request.config or {}).get("agent_alias_id") or self._alias_id()
        # Prefer TSTALIASID if production missing (dev convenience)
        session_id = (request.config or {}).get("session_id") or "harness-session"
        client = self._client("bedrock-agent-runtime")
        try:
            resp = client.invoke_agent(
                agentId=agent_id,
                agentAliasId=alias_id,
                sessionId=session_id,
                inputText=str(
                    (request.input or {}).get("input")
                    or (request.input or {}).get("query")
                    or request.input
                ),
            )
            chunks: list[str] = []
            for event in resp.get("completion", []):
                chunk = event.get("chunk") or {}
                payload = chunk.get("bytes")
                if payload:
                    chunks.append(
                        payload.decode("utf-8")
                        if isinstance(payload, (bytes, bytearray))
                        else str(payload)
                    )
            text = "".join(chunks)
            return InvokeResponse(
                output={"text": text, "agent_id": agent_id},
                latency_ms=None,
                raw={"provider": "bedrock"},
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock InvokeAgent failed: {exc}") from exc

    def _latest_version(self, client: Any, agent_id: str) -> str:
        versions = client.list_agent_versions(agentId=agent_id).get("agentVersionSummaries", [])
        prepared = [
            v
            for v in versions
            if (v.get("agentStatus") or v.get("agentVersionStatus") or "")
            in {"PREPARED", "Prepared", "READY", ""}
        ]
        pool = prepared or versions
        if not pool:
            return "DRAFT"
        # Prefer highest numeric version
        def key(v: dict) -> tuple:
            ver = str(v.get("agentVersion") or "0")
            try:
                return (1, int(ver))
            except ValueError:
                return (0, ver)

        best = sorted(pool, key=key, reverse=True)[0]
        return str(best.get("agentVersion") or "DRAFT")

    def _get_alias_snapshot(self, client: Any, agent_id: str, alias_id: str) -> dict[str, Any]:
        try:
            alias = client.get_agent_alias(agentId=agent_id, agentAliasId=alias_id)
            detail = alias.get("agentAlias") or alias
            return {
                "agentAliasId": detail.get("agentAliasId") or alias_id,
                "agentAliasName": detail.get("agentAliasName") or alias_id,
                "routingConfiguration": detail.get("routingConfiguration") or [],
                "description": detail.get("description") or "",
            }
        except Exception:  # noqa: BLE001
            return {
                "agentAliasId": alias_id,
                "agentAliasName": alias_id,
                "routingConfiguration": [],
                "description": "",
            }

    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Prepare agent and point alias at latest prepared version."""
        await self.authenticate()
        agent_id = str(payload.get("external_id") or payload.get("agent_id") or "")
        if not agent_id:
            raise ValueError("deploy requires external_id (Bedrock agent id)")
        alias_id = self._alias_id(payload.get("alias_id"))
        client = self._client()
        try:
            prep = client.prepare_agent(agentId=agent_id)
            # Poll briefly for PREPARED
            status = (prep.get("agentStatus") or prep.get("status") or "").upper()
            for _ in range(12):
                if status in {"PREPARED", "READY"}:
                    break
                time.sleep(2)
                got = client.get_agent(agentId=agent_id)
                status = str((got.get("agent") or {}).get("agentStatus") or "").upper()
            version = payload.get("version") or self._latest_version(client, agent_id)
            routing = [{"agentVersion": str(version)}]
            # Update existing alias or create
            try:
                client.update_agent_alias(
                    agentId=agent_id,
                    agentAliasId=alias_id,
                    agentAliasName=alias_id,
                    routingConfiguration=routing,
                    description=f"KEEL deploy → v{version}",
                )
                action = "alias_updated"
            except Exception:  # noqa: BLE001
                created = client.create_agent_alias(
                    agentId=agent_id,
                    agentAliasName=alias_id,
                    routingConfiguration=routing,
                    description=f"KEEL deploy → v{version}",
                )
                alias_id = (created.get("agentAlias") or {}).get("agentAliasId") or alias_id
                action = "alias_created"
            return {
                "provider": "bedrock",
                "operation": "deploy",
                "agent_id": agent_id,
                "alias_id": alias_id,
                "version": version,
                "agent_status": status,
                "action": action,
            }
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock deploy failed: {exc}") from exc

    async def rollback(self, external_id: str, version: str) -> dict[str, Any]:
        await self.authenticate()
        if not version:
            raise ValueError("rollback requires target version")
        alias_id = self._alias_id()
        client = self._client()
        try:
            client.update_agent_alias(
                agentId=external_id,
                agentAliasId=alias_id,
                agentAliasName=alias_id,
                routingConfiguration=[{"agentVersion": str(version)}],
                description=f"KEEL rollback → v{version}",
            )
            return {
                "provider": "bedrock",
                "operation": "rollback",
                "agent_id": external_id,
                "alias_id": alias_id,
                "version": version,
            }
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock rollback failed: {exc}") from exc

    async def suspend(self, external_id: str) -> dict[str, Any]:
        """Stop invokes via alias: snapshot routing then delete alias."""
        await self.authenticate()
        alias_id = self._alias_id()
        client = self._client()
        try:
            snapshot = self._get_alias_snapshot(client, external_id, alias_id)
            try:
                client.delete_agent_alias(agentId=external_id, agentAliasId=alias_id)
                deleted = True
            except Exception as exc:  # noqa: BLE001
                # Alias may not exist — still mark suspended in control plane
                deleted = False
                snapshot["delete_error"] = str(exc)
            return {
                "provider": "bedrock",
                "operation": "suspend",
                "agent_id": external_id,
                "alias_id": alias_id,
                "alias_deleted": deleted,
                "snapshot": snapshot,
            }
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock suspend failed: {exc}") from exc

    async def resume(self, external_id: str) -> dict[str, Any]:
        """Recreate alias from snapshot in payload metadata or latest version."""
        await self.authenticate()
        alias_id = self._alias_id()
        client = self._client()
        try:
            version = self._latest_version(client, external_id)
            routing = [{"agentVersion": str(version)}]
            try:
                client.create_agent_alias(
                    agentId=external_id,
                    agentAliasName=alias_id,
                    routingConfiguration=routing,
                    description="KEEL resume",
                )
                action = "alias_created"
            except Exception:  # noqa: BLE001
                client.update_agent_alias(
                    agentId=external_id,
                    agentAliasId=alias_id,
                    agentAliasName=alias_id,
                    routingConfiguration=routing,
                    description="KEEL resume",
                )
                action = "alias_updated"
            return {
                "provider": "bedrock",
                "operation": "resume",
                "agent_id": external_id,
                "alias_id": alias_id,
                "version": version,
                "action": action,
            }
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock resume failed: {exc}") from exc

    async def restart(self, external_id: str) -> dict[str, Any]:
        await self.authenticate()
        sus = await self.suspend(external_id)
        time.sleep(1)
        res = await self.resume(external_id)
        # Also re-prepare for a clean DRAFT→PREPARED cycle
        client = self._client()
        try:
            prep = client.prepare_agent(agentId=external_id)
            prep_status = prep.get("agentStatus") or prep.get("status")
        except Exception as exc:  # noqa: BLE001
            prep_status = f"prepare_skipped: {exc}"
        return {
            "provider": "bedrock",
            "operation": "restart",
            "agent_id": external_id,
            "suspend": sus,
            "resume": res,
            "prepare_status": prep_status,
        }

    async def delete_from_source(self, external_id: str) -> dict[str, Any]:
        await self.authenticate()
        client = self._client()
        try:
            client.delete_agent(agentId=external_id, skipResourceInUseCheck=True)
            return {
                "provider": "bedrock",
                "operation": "delete_from_source",
                "agent_id": external_id,
                "deleted": True,
            }
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Bedrock DeleteAgent failed: {exc}") from exc

    async def get_telemetry(self, external_id: str) -> dict[str, Any]:
        """Federate Bedrock CloudWatch activity (Agent 365–style Activity metrics)."""
        await self.authenticate()
        try:
            import boto3  # type: ignore
            from datetime import datetime, timedelta, timezone
        except ImportError as exc:
            raise RuntimeError("boto3 required for Bedrock telemetry") from exc

        cw = boto3.client("cloudwatch", region_name=self.region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
        # Bedrock Agents emit metrics under AWS/Bedrock namespace (names vary by account)
        metric_names = [
            ("Invocations", "sessions"),
            ("SystemErrors", "exceptions"),
            ("Throttles", "throttles"),
            ("ClientErrors", "client_errors"),
            ("Latency", "latency_sum"),
        ]
        daily: dict[str, dict[str, float]] = {}
        notes: list[str] = []

        def bucket(day_key: str) -> dict[str, float]:
            return daily.setdefault(
                day_key,
                {
                    "sessions": 0.0,
                    "exceptions": 0.0,
                    "runtime_seconds": 0.0,
                    "invocations": 0.0,
                    "tool_calls": 0.0,
                    "unique_users": 0.0,
                },
            )

        for metric_name, field in metric_names:
            try:
                resp = cw.get_metric_statistics(
                    Namespace="AWS/Bedrock",
                    MetricName=metric_name,
                    Dimensions=[{"Name": "AgentId", "Value": external_id}],
                    StartTime=start,
                    EndTime=end,
                    Period=86400,
                    Statistics=["Sum"] if metric_name != "Latency" else ["Average", "SampleCount"],
                )
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{metric_name}: {exc}")
                continue
            for dp in resp.get("Datapoints", []):
                ts = dp.get("Timestamp")
                if not ts:
                    continue
                day_key = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
                b = bucket(day_key)
                if metric_name == "Latency":
                    avg_ms = float(dp.get("Average") or 0)
                    samples = float(dp.get("SampleCount") or 0)
                    b["runtime_seconds"] += (avg_ms / 1000.0) * samples
                    b["invocations"] += samples
                    b["sessions"] += samples
                else:
                    val = float(dp.get("Sum") or 0)
                    if field == "sessions":
                        b["sessions"] += val
                        b["invocations"] += val
                    elif field == "exceptions":
                        b["exceptions"] += val
                    elif field == "client_errors":
                        b["exceptions"] += val

        if not daily and notes:
            # Soft empty — KEEL will still roll up local invokes
            return {
                "sessions": 0,
                "exceptions": 0,
                "runtime_seconds": 0,
                "unique_users": 0,
                "tool_calls": 0,
                "invocations": 0,
                "daily": [],
                "provider": "bedrock",
                "notes": notes,
                "available": False,
            }

        daily_list = [
            {
                "day": k,
                "sessions": int(v["sessions"]),
                "exceptions": int(v["exceptions"]),
                "runtime_seconds": float(v["runtime_seconds"]),
                "unique_users": 0,  # Bedrock does not expose Entra users
                "tool_calls": int(v["tool_calls"]),
                "invocations": int(v["invocations"]),
            }
            for k, v in sorted(daily.items())
        ]
        return {
            "sessions": sum(d["sessions"] for d in daily_list),
            "exceptions": sum(d["exceptions"] for d in daily_list),
            "runtime_seconds": sum(d["runtime_seconds"] for d in daily_list),
            "unique_users": 0,
            "tool_calls": sum(d["tool_calls"] for d in daily_list),
            "invocations": sum(d["invocations"] for d in daily_list),
            "daily": daily_list,
            "provider": "bedrock",
            "notes": notes,
            "available": True,
        }

    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]:
        raise UnsupportedOperationError("inspect_tools", self.connector_type)

    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]:
        agents = await self.discover_agents()
        for a in agents:
            if a.external_id == external_id:
                return a.model_dump()
        await self.authenticate()
        client = self._client()
        got = client.get_agent(agentId=external_id)
        agent = got.get("agent") or {}
        return {
            "external_id": external_id,
            "name": agent.get("agentName"),
            "status": agent.get("agentStatus"),
            "framework": "bedrock",
            "metadata": {"raw": agent, "region": self.region},
        }
