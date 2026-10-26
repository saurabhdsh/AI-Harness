# TCS AI Harness — Reference Agents

Lightweight FastAPI agents for demos and connector integration tests.

| Agent | Directory | Port | Role |
|-------|-----------|------|------|
| LangGraph OpenAI / Azure | `langgraph-openai-agent/` | **8090** | Local LLM code agent (no Docker) |
| **Domain AD / AMS / QE** | `domain-agents/` | **8091** | User stories, sprint, tech design, AMS incident/change, QE tests/defects |
| LangGraph AD Code Engineering | `langgraph-agent/` | **8080** | Primary Compose demo — AST analysis + patches |
| REST AMS Incident | `rest-agent/` | **8082** | Keyword RCA / remediation |
| QE Test | `qe-test-agent/` | **8083** | Pytest stub generation + validation |
| AMS Digital Twin | `ams-incident-agent/` | **8084** | Synthetic incidents + proxy to rest-agent |

Offline stubs (`langgraph-agent`, `rest-agent`, …) need no API keys.
`domain-agents` and `langgraph-openai-agent` need Azure OpenAI or OpenAI keys in root `.env`.

```bash
# Domain LLM agents (AD / AMS / QE)
cd domain-agents && pip install -r requirements.txt && uvicorn main:app --port 8091

# Compose primary demo
cd langgraph-agent && pip install -r requirements.txt && uvicorn main:app --port 8080
```
