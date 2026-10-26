# Service Map

| Module | Location | Status | Notes |
|--------|----------|--------|-------|
| Mission Control UI | `apps/mission-control` | Implemented | SEAL-matched UI |
| Control Plane API | `services/control-plane` | Implemented | Consolidated modules |
| LangGraph connector | `app/connectors/langgraph.py` | Implemented | Real HTTP |
| Generic REST connector | `app/connectors/generic_rest.py` | Implemented | Real HTTP |
| AD LangGraph agent | `examples/langgraph-agent` | Implemented | Offline deterministic |
| AMS REST agent | `examples/rest-agent` | Implemented | Rule-based RCA |
| QE test agent | `examples/qe-test-agent` | Implemented | Pytest stub gen |
| AMS digital twin | `examples/ams-incident-agent` | Implemented | Synthetic events |
| Identity / Tenant | control-plane modules | Partial | Demo JWT + tenant scoping |
| Evaluation engine | control-plane | Implemented | Deterministic + optional judge |
| Deployment service | — | Planned | Unsupported on LangGraph connector |
| Temporal orchestration | — | Planned | Phase 6+ |
| Weave / QEVAL / TokenOps | `integrations/*` | Contract stubs | Blocked on real APIs |
| ClickHouse / Vault / OPA | — | Planned | Phase 8 hardening |
