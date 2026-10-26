# AgentConnector Protocol (TCS AI Harness)

This document describes the **AgentConnector** protocol used by the control plane to
discover, inspect, and invoke external agents. Implementation source of truth:

`services/control-plane/app/connectors/base.py`

Reference agents that speak this shape live under `examples/`:

| Example | Port | Connector type |
|---------|------|----------------|
| `examples/langgraph-agent` | 8080 | `langgraph` |
| `examples/rest-agent` | 8082 | `generic_rest` |
| `examples/qe-test-agent` | 8083 | `generic_rest` |
| `examples/ams-incident-agent` | 8084 | `generic_rest` (+ digital twin) |

---

## CapabilityManifest

Boolean capability flags returned by `get_capabilities()`:

| Field | Meaning |
|-------|---------|
| `discovery` | Can list agents (`discover_agents`) |
| `metadata` | Can fetch per-agent metadata |
| `invocation` | Can invoke (`invoke_agent`) |
| `telemetry` | Can fetch runtime telemetry |
| `evaluation` | Evaluation / scoring hooks |
| `deployment` | Remote deploy support |
| `rollback` | Version rollback |
| `suspension` | Suspend / pause agent |
| `tool_inspection` | List tools/functions exposed by the agent |
| `credential_requirements` | Names of secrets required (e.g. `secret_ref`) |
| `restrictions` | Human-readable unsupported operations |

Unsupported operations **must** raise `UnsupportedOperationError` — never silently mock success.

---

## Models

### DiscoveredAgent

```text
external_id: str
name: str
framework: str | None          # e.g. "langgraph", "rest"
invoke_url: str | None
metadata: dict[str, Any]
```

### InvokeRequest

```text
input: dict[str, Any]
config: dict[str, Any]
external_id: str | None
invoke_url: str | None
```

### InvokeResponse

```text
output: dict[str, Any]
latency_ms: float | None
token_input: int | None
token_output: int | None
trace_id: str | None
raw: dict[str, Any]
```

---

## AgentConnector (Protocol)

```python
@runtime_checkable
class AgentConnector(Protocol):
    connector_type: str

    async def authenticate(self) -> bool: ...
    async def discover_agents(self) -> list[DiscoveredAgent]: ...
    async def get_agent_metadata(self, external_id: str) -> dict[str, Any]: ...
    async def get_capabilities(self) -> CapabilityManifest: ...
    async def invoke_agent(self, request: InvokeRequest) -> InvokeResponse: ...
    async def get_telemetry(self, external_id: str) -> dict[str, Any]: ...
    async def deploy(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def rollback(self, external_id: str, version: str) -> dict[str, Any]: ...
    async def suspend(self, external_id: str) -> dict[str, Any]: ...
    async def inspect_tools(self, external_id: str) -> list[dict[str, Any]]: ...
```

Built-in control-plane implementations:

- **`generic_rest`** — HTTP discovery (`GET /agents` or OpenAPI) + `POST /invoke`
- **`langgraph`** — Same as REST, tries `/invoke`, `/runs`, `/runs/wait`

---

## HTTP contract for reference agents

Agents should expose (subset is OK; connectors fall back gracefully):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness / authenticate probe |
| `GET` | `/agents` | Discovery list: `[{id, name, framework, capabilities}]` |
| `GET` | `/agents/{id}` | Metadata |
| `POST` | `/invoke` | Invocation |
| `POST` | `/runs` | LangGraph-style alias (optional) |
| `GET` | `/openapi.json` | Auto from FastAPI — used as discovery fallback |

### Invoke request (typical)

```json
{
  "input": { "...": "agent-specific" },
  "agent_id": "optional-external-id",
  "config": {}
}
```

`input` may also be a plain string; connectors wrap non-dict outputs.

### Invoke response (recommended)

```json
{
  "output": { "...": "structured result" },
  "messages": [{ "role": "assistant", "content": "..." }],
  "metadata": {
    "latency_ms": 12.5,
    "model": "deterministic-ast",
    "run_id": "uuid"
  }
}
```

The control plane maps `output` / `result` / `values` into `InvokeResponse.output`
and records `latency_ms` from wall clock (and optionally from metadata).

---

## Wiring a connector

1. Run a reference agent (e.g. `examples/langgraph-agent` on `:8080`).
2. Register a connector in the control plane with `base_url` pointing at the agent
   and `connector_type` of `langgraph` or `generic_rest`.
3. Call discover → metadata → invoke through Mission Control or the control-plane API.

No SDK package install is required for demos — implement the HTTP contract above
and the existing connectors will talk to your agent.
