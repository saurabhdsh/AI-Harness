"""Connector factory registry."""

from __future__ import annotations

from typing import Any

from app.connectors.aws_bedrock import AWSBedrockConnector
from app.connectors.azure_foundry import AzureFoundryConnector
from app.connectors.crewai import CrewAIConnector
from app.connectors.generic_rest import GenericRESTConnector
from app.connectors.langgraph import LangGraphConnector
from app.connectors.mulesoft import MuleSoftConnector
from app.connectors.servicenow import ServiceNowConnector

_REGISTRY: dict[str, type] = {
    "generic_rest": GenericRESTConnector,
    "rest": GenericRESTConnector,
    "generic": GenericRESTConnector,
    "langgraph": LangGraphConnector,
    "crewai": CrewAIConnector,
    "aws_bedrock": AWSBedrockConnector,
    "bedrock": AWSBedrockConnector,
    "azure_foundry": AzureFoundryConnector,
    "azure": AzureFoundryConnector,
    "microsoft_foundry": AzureFoundryConnector,
    "servicenow": ServiceNowConnector,
    "service_now": ServiceNowConnector,
    "sn": ServiceNowConnector,
    "mulesoft": MuleSoftConnector,
    "mule": MuleSoftConnector,
    "anypoint": MuleSoftConnector,
    "agent_fabric": MuleSoftConnector,
}


def list_connector_types() -> list[dict[str, str]]:
    meta = {
        "langgraph": "LangGraph / LangChain graph agents over HTTP",
        "crewai": "CrewAI crews exposed via REST",
        "generic_rest": "Generic REST / OpenAPI agent services",
        "aws_bedrock": "AWS Bedrock Agents (requires AWS credentials)",
        "azure_foundry": "Azure AI Foundry / Agents (requires Azure credentials)",
        "servicenow": "ServiceNow AI Agents / Agent Studio (instance credentials)",
        "mulesoft": "MuleSoft Agent Fabric / Anypoint (OAuth + runtime URL)",
    }
    # unique by class
    seen: set[type] = set()
    out: list[dict[str, str]] = []
    for key, cls in sorted(_REGISTRY.items()):
        if cls in seen:
            continue
        if key in {
            "rest",
            "generic",
            "bedrock",
            "azure",
            "microsoft_foundry",
            "service_now",
            "sn",
            "mule",
            "anypoint",
            "agent_fabric",
        }:
            continue
        seen.add(cls)
        out.append({"id": key, "label": meta.get(key, key), "connector_type": key})
    return out


def get_connector(
    connector_type: str,
    *,
    base_url: str,
    secret_ref: str | None = None,
    **kwargs: Any,
):
    key = connector_type.lower().strip()
    cls = _REGISTRY.get(key)
    if cls is None:
        supported = ", ".join(sorted({c["id"] for c in list_connector_types()}))
        raise ValueError(
            f"Unknown connector type '{connector_type}'. Supported: {supported}"
        )
    return cls(base_url=base_url, secret_ref=secret_ref, **kwargs)
