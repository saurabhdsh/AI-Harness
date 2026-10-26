# Architecture Decisions

## ADR-001 — Consolidated control plane

**Decision:** Ship one FastAPI control-plane service with domain modules instead of 20+ microservices for Phase 0–1.  
**Why:** Faster vertical slice, shared transactions, simpler local Compose. Interfaces remain separable.

## ADR-002 — SEAL visual system

**Decision:** Mission Control UI matches SEAL’s Apple-light design (Inter, `#0071e3`, 220px muted text rail), not the dark charcoal/aubergine palette described in the product brief.  
**Why:** Explicit user instruction: use UI design exactly like SEAL.

## ADR-003 — Capability-honest connectors

**Decision:** Connectors declare manifests and raise `UnsupportedOperationError` for missing ops.  
**Why:** Prevents fake deployment/success claims.

## ADR-004 — Offline-first reference agents

**Decision:** AD LangGraph agent uses deterministic AST/heuristic analysis without requiring LLM keys.  
**Why:** Demo and CI must work without cloud credentials; optional LLM enrichment is opt-in.

## ADR-005 — No silent mocks

**Decision:** Missing credentials or APIs surface errors; tests may mock httpx explicitly, production paths never substitute fake success data.
