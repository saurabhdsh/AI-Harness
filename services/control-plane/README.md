# TCS AI Harness — Control Plane

FastAPI control-plane backend: agent registry, connectors, real HTTP invocation, evaluations, audit, mission overview.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL + asyncpg, Alembic
- JWT auth (demo: `admin@harness.local` / `harness-admin` when `AUTH_DEMO=true`)
- Connectors: `generic_rest`, `langgraph` — unsupported ops raise `UnsupportedOperationError`

## Quick start

```bash
cd services/control-plane
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
# With Postgres up:
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

Demo mode also runs `create_all` + admin seed on startup when `AUTO_CREATE_TABLES=true` and `AUTH_DEMO=true`.

## Tests

```bash
PYTHONPATH=. pytest -q
```

## Key APIs (`/api/v1`)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Liveness |
| POST | `/auth/login` | `{email,password}` → JWT |
| CRUD | `/agents` | Registry |
| GET | `/agents/{id}/capabilities` | Connector manifest |
| POST | `/agents/{id}/invoke` | Real HTTP invoke |
| POST | `/agents/{id}/deploy` | Typed 501 if unsupported |
| GET/POST | `/connectors` | Platform connections |
| POST | `/connectors/{id}/validate` | Live auth + discover |
| POST | `/onboarding/jobs` | Connect + discover + register |
| POST | `/evaluations` | Deterministic (+ optional LLM judge) |
| GET | `/executions` | Execution history |
| GET | `/traces/{id}` | Trace spans |
| GET | `/mission/overview` | Fleet aggregates from DB |
| GET | `/audit-events` | Immutable audit log |
