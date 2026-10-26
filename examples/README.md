# TCS AI Harness — Reference Agents

Lightweight FastAPI agents for demos and connector integration tests.

| Agent | Directory | Port | Role |
|-------|-----------|------|------|
| LangGraph AD Code Engineering | `langgraph-agent/` | **8080** | Primary demo — AST analysis + patches |
| REST AMS Incident | `rest-agent/` | **8082** | Keyword RCA / remediation |
| QE Test | `qe-test-agent/` | **8083** | Pytest stub generation + validation |
| AMS Digital Twin | `ams-incident-agent/` | **8084** | Synthetic incidents + proxy to rest-agent |

All agents are dependency-light (`fastapi`, `uvicorn`, `pydantic`) and run offline
without API keys. See `connectors/connector-sdk/README.md` for the AgentConnector protocol.

```bash
# Primary demo
cd langgraph-agent && pip install -r requirements.txt && uvicorn main:app --port 8080
```
