# Implementation Status

Updated: 2026-10-26

| Area | Status | Evidence |
|------|--------|----------|
| Monorepo layout | Implemented | Root tree |
| Architecture docs | Implemented | `docs/architecture/*` |
| Control-plane API | Implemented | `services/control-plane` — pytest 7/7 reported by builder |
| Auth (demo JWT) | Implemented | `/api/v1/auth/login` |
| Agent registry | Implemented | CRUD + tenant scope |
| Connectors (LangGraph, REST) | Implemented | Real httpx; deploy → 501 typed |
| Onboarding jobs | Implemented | `/api/v1/onboarding/jobs` |
| Smart project detect (path/zip) | Implemented | `/api/v1/onboarding/detect/path`, `/detect/upload`, `/projects` |
| Framework connectors | Partial | LangGraph, CrewAI, REST live; Bedrock/Foundry capability-honest (need creds) |
| Evaluation engine | Implemented | Deterministic scoring; optional judge refuses mock |
| Execution + traces | Implemented | Persisted executions/spans |
| Mission overview | Implemented | Real DB aggregates |
| Mission Control UI (SEAL) | Implemented | `apps/mission-control` — build succeeded |
| Reference agents | Implemented | `examples/*` |
| Docker Compose | Implemented | `docker-compose.yml` |
| Weave / QEVAL / TokenOps | Planned / blocked | Adapter stubs only |
| Temporal / Kafka / ClickHouse | Planned | — |
| Cloud connectors | Planned | Phase 7 |
| K8s / Helm | Planned | Phase 8 |

## First product milestone

**An externally developed agent is onboarded, invoked, evaluated, observed and governed without rewriting its implementation.**

**Verified locally (2026-10-26) via `scripts/smoke-test.sh`:**

- LangGraph AD agent healthy on `:8080`
- Control plane healthy on `:8000`
- Login → list agents → invoke (`status=succeeded`) → trace spans → evaluation (`score=1.0`) → mission overview aggregates
- Backend pytest: **7 passed**
- Frontend production build: **succeeded**
- Mission Control UI: http://127.0.0.1:5173

Path: seed/onboard LangGraph agent → invoke → evaluate → observe in Mission Control / Observatory.
