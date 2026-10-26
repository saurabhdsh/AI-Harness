# Universal Agent Connector Contract

## Protocol

Connectors implement a capability-based interface. Unsupported operations raise `UnsupportedOperationError` — never a fabricated success.

```python
class AgentConnector(Protocol):
    async def authenticate(self, config): ...
    async def discover_agents(self, scope=None): ...
    async def get_agent_metadata(self, agent_id): ...
    async def get_capabilities(self) -> CapabilityManifest: ...
    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse: ...
    async def get_execution_status(self, execution_id): ...
    async def get_telemetry(self, agent_id, query): ...
    async def deploy_agent(self, artifact, target): ...
    async def rollback_agent(self, deployment_id): ...
    async def suspend_agent(self, agent_id): ...
```

## Capability manifest

| Field | Meaning |
|-------|---------|
| discovery | List agents from platform |
| metadata | Inspect agent metadata |
| invocation | Invoke agent |
| telemetry | Pull platform telemetry |
| evaluation | Safe to use for evaluation runs |
| deployment | Native deploy supported |
| rollback | Native rollback supported |
| suspension | Native suspend supported |
| tool_inspection | List agent tools |
| credential_requirements | Required secret refs |
| restrictions | Human-readable limits |

## Implemented connectors

| Type | Discovery | Invoke | Deploy | Notes |
|------|-----------|--------|--------|-------|
| `langgraph` | Yes (`/agents`) | Yes (`/invoke`, `/runs`) | **No** | Typed unsupported |
| `generic_rest` / `rest` | Best-effort | Yes | **No** | OpenAPI/`/agents` when present |

## Onboarding paths (current)

1. Framework adapter (LangGraph) — working
2. REST/OpenAPI — working
3. Manual registration with declared limitations — working via agent create API
4. Cloud native (Bedrock, Foundry, Copilot Studio) — planned Phase 7
5. MCP / A2A — planned; MCP is **not** treated as universal management

See `connectors/connector-sdk/README.md` and `services/control-plane/app/connectors/`.
