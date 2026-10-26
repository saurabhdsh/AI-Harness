# Domain Agents — AD / AMS / QE

One FastAPI process (port **8091**) exposing LLM agents for Application Development,
Application Management Services, and Quality Engineering.

| Agent id | Name | Domain |
|----------|------|--------|
| `ad-user-story` | AD User Story Author | AD / SDLC |
| `ad-sprint-planner` | AD Sprint Planner | AD / SDLC |
| `ad-tech-design` | AD Tech Design Author | AD / SDLC |
| `ams-incident-analyst` | AMS Incident Analyst | AMS |
| `ams-change-assessor` | AMS Change Assessor | AMS |
| `qe-test-designer` | QE Test Designer | QE |
| `qe-defect-triage` | QE Defect Triage | QE |

Uses the same Azure OpenAI / OpenAI keys as the root `.env`.

## Run

```bash
cd examples/domain-agents
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# keys from repo-root .env (or copy .env.example)
uvicorn main:app --host 127.0.0.1 --port 8091
```

From repo root (after `make setup-local`): `make domain-agents`

`make dev-local` also starts this service on **8091**.

## Invoke

Per-agent URL (preferred for Harness registration):

```bash
curl -s http://127.0.0.1:8091/agents/ad-user-story/invoke \
  -H 'Content-Type: application/json' \
  -d '{"input":{"use_sample":true}}'
```

Shared `/invoke` (pass `agent_id`):

```bash
curl -s http://127.0.0.1:8091/invoke -H 'Content-Type: application/json' \
  -d '{"agent_id":"ams-incident-analyst","input":{"use_sample":true}}'
```

## Onboard into Harness

```bash
# control-plane + domain-agents must be running
chmod +x scripts/register-domain-agents.sh
./scripts/register-domain-agents.sh
```

Or Onboarding Studio → URL `http://127.0.0.1:8091` → LangGraph / Generic REST.
`GET /agents` lists all seven with per-agent `invoke_url`.
