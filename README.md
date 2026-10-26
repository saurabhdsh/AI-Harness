# TCS AI Harness Engineering Platform

**Build Anywhere. Engineer Centrally. Deploy Anywhere. Govern Everything.**

Federated AI agent engineering, governance, and operations control plane for AD, AMS, and QE. Onboard externally developed agents without rewriting them.

## Quick start

```bash
# Prerequisites: Docker, Node 20+, Python 3.12+
cp .env.example .env
make setup          # optional local venvs + npm install

# Start data plane + control plane + reference agent, then UI
docker compose up --build -d postgres redis langgraph-agent control-plane seed
cd apps/mission-control && npm install && npm run dev
```

Or: `make dev` (Compose backend + Vite frontend).

| Surface | URL |
|---------|-----|
| Mission Control | http://localhost:5173 |
| Control Plane API | http://localhost:8000/docs |
| LangGraph AD agent | http://localhost:8080/docs |

**Demo login:** `admin@harness.local` / `harness-admin`

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
| `make setup` | Install local dependencies |
| `make dev` | Compose + Vite |
| `make test` | Backend pytest + frontend build |
| `make migrate` | Alembic upgrade |
| `make seed-demo` | Register demo tenant + AD agent |
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
