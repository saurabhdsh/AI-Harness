# TCS AI Harness — Architecture

**Product:** TCS AI Harness Engineering Platform  
**Positioning:** Build Anywhere. Engineer Centrally. Deploy Anywhere. Govern Everything.  
**Category:** Federated AI Agent Engineering, Governance and Operations Control Plane

## Core promise

Onboard an externally developed agent without rewriting it. Invoke, evaluate, observe, and govern it through a vendor-neutral control plane.

## Architectural principles

1. Vendor-neutral — no mandatory hyperscaler lock-in
2. Customer-owned execution environments
3. API-first integration
4. Framework-independent agent connectivity
5. Pluggable evaluation and governance
6. Enterprise security by default
7. Real persistence and real execution
8. Explicit unsupported / simulated capability labeling
9. Auditable control-plane operations
10. No silent fallback from real integrations to mock data

## Deployable topology (Phase 0–1)

Rather than dozens of independently deployed microservices, closely related domains are consolidated into a **control-plane** FastAPI application with clean module boundaries for later separation.

```
┌─────────────────────────────────────────────────────────────┐
│  Mission Control UI (React / Vite) — SEAL design system     │
└────────────────────────────┬────────────────────────────────┘
                             │ /api/v1
┌────────────────────────────▼────────────────────────────────┐
│  Control Plane (FastAPI)                                    │
│  registry · onboarding · connectors · evaluation            │
│  execution · observability · audit · auth · costs           │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
  PostgreSQL        Redis      Reference agents
                               (LangGraph / REST / QE / AMS)
```

Optional integrations (Weave, QEVAL/Noryx, TokenOps) are adapter interfaces only until real customer API contracts are supplied.

## Frontend

- React 18 + TypeScript + Vite + Tailwind
- Visual language copied from **SEAL** (Apple-light: Inter, `#0071e3`, 220px muted text rail)
- TanStack Query + Zustand

## Backend

- Python 3.12, FastAPI, SQLAlchemy async, Alembic, PostgreSQL
- Connector SDK with capability manifests and typed `UnsupportedOperationError`
- JWT demo auth (OIDC-ready configuration path)

## Local vs enterprise

- **Local:** Docker Compose (`make dev`)
- **Enterprise:** Kubernetes/Helm planned in Phase 8 — not required for developer environment
