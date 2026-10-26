# Known Limitations

1. **Demo auth only** — OIDC IdP not wired; use `AUTH_DEMO` for local.
2. **Secrets** — `secret_ref` is opaque; Vault resolver not implemented.
3. **Redis** — configured but not yet used for cache/queues.
4. **Deploy/rollback/suspend** — unsupported on LangGraph/REST connectors; returns typed errors.
5. **Cost rates** — placeholder coefficients; labeled as estimates, not provider invoices. Admin can configure budgets; FinOps shows period-aware spend vs limit (not hard enforcement / TokenOps).
6. **LLM-as-judge** — requires `LLM_JUDGE_URL`; missing URL does not fake scores.
7. **Weave / QEVAL / TokenOps** — no invented endpoints; adapters await real contracts.
8. **Temporal orchestration** — not yet running; Workflow UI is honest EmptyState.
9. **Release Command** — Gated release trains are real (evaluation + approval → environment/lifecycle promote). Native platform deploy/rollback remains unsupported on current connectors (metadata promote only; deploy recorded as skipped).
10. **Mission Control topology** — constellation from registered agents; dependency edges limited until interaction graph enrichment.
