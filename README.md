# TCS AI Harness Engineering Platform

**Build Anywhere. Engineer Centrally. Deploy Anywhere. Govern Everything.**

Federated AI agent engineering, governance, and operations control plane for AD, AMS, and QE. Onboard externally developed agents without rewriting them.

## Quick start

### Without Docker (recommended for laptops)

Needs only **Python 3.11+** and **Node 20+**. Uses **SQLite** — no Postgres/Redis/Docker.

```bash
git clone https://github.com/saurabhdsh/AI-Harness.git
cd AI-Harness
cp .env.example .env
# Edit .env — Azure OpenAI (other Mac) or OPENAI_API_KEY
make setup-local
make dev-local
```

Stop with `make stop-local`. Logs under `data/logs/`.

### With Docker

```bash
cp .env.example .env
make setup
make dev          # Compose + Vite
```

| Surface | URL |
|---------|-----|
| Mission Control | http://localhost:5173 |
| Control Plane API | http://localhost:8000/docs |
| LangGraph AD agent | http://localhost:8090/docs |

**Demo login:** `admin@harness.local` / `harness-admin`

### LLM credentials (`.env`)

Azure OpenAI (same as `test_llm.py`):

```bash
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-5-mini
OPENAI_MODEL=gpt-5-mini
```

Or public OpenAI: `OPENAI_API_KEY` + `OPENAI_MODEL`.

## First milestone demo

1. Sign in to Mission Control
2. Open **Agent Universe** — see the seeded AD Code Engineering Agent
3. Open the agent profile → **Invoke** with `{ "task": "improve", "use_sample": true }`
4. Open **Live Observatory** — inspect the real execution trace
5. Open **Evaluation Lab** — run the default suite against the agent
6. Return to **Mission Control** — fleet metrics update from the database

```bash
chmod +x scripts/smoke-test.sh
make smoke-test
```

## Repository layout

```
apps/mission-control/     # SEAL-matched React control UI
services/control-plane/   # FastAPI federated control plane
examples/                 # External reference agents (not rebuilt inside Harness)
connectors/               # Connector SDK docs + adapters
integrations/             # Weave / QEVAL / TokenOps contracts
docs/                     # Architecture + status
```

## Commands

| Command | Purpose |
|---------|---------|
| `make setup` / `setup-local` | Install local dependencies |
| `make dev-local` | **No Docker** — SQLite + agent + API + UI |
| `make stop-local` | Stop no-Docker processes |
| `make dev` | Docker Compose + Vite |
| `make test` | Backend pytest + frontend build |
| `make migrate` | Alembic upgrade |
| `make seed-demo` | Register demo tenant + AD agent (Compose) |
| `make smoke-test` | End-to-end API smoke |
| `make down` | Stop Compose |

## UI design

Mission Control uses the **SEAL** visual system: Apple-light greys, Inter + JetBrains Mono, accent `#0071e3`, 220px muted text navigation rail.

## Documentation

- [Architecture](docs/architecture/ARCHITECTURE.md)
- [Service map](docs/architecture/SERVICE_MAP.md)
- [Connector contract](docs/architecture/CONNECTOR_CONTRACT.md)
- [Security model](docs/architecture/SECURITY_MODEL.md)
- [Data model](docs/architecture/DATA_MODEL.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
