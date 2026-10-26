# Security Model

## Current (Phase 0–1)

- Tenant-scoped database rows (`tenant_id` on all control-plane entities)
- JWT bearer auth (`AUTH_DEMO=true` seeds `admin@harness.local`)
- Passwords hashed with bcrypt
- Connector credentials stored as `secret_ref` only — **no plaintext secrets in application tables**
- Agent responses treated as untrusted data
- Unsupported privileged ops (deploy/rollback/suspend) fail closed with typed errors
- Audit events written for registry, invoke, evaluation, and onboarding actions
- CORS allowlist via `CORS_ORIGINS`
- Evaluation LLM-judge never invents a pass when the judge URL is missing

## Planned

- Enterprise OIDC/OAuth2 IdP
- RBAC + ABAC with Open Policy Agent
- HashiCorp Vault (or approved secret manager) resolution of `secret_ref`
- Workload identities for connectors
- SSRF protections on connector base URLs (egress allowlists)
- Rate limiting and immutable audit store
- TLS everywhere; encryption at rest for Postgres

## Non-negotiable rules

1. Agents cannot grant themselves additional privileges
2. LLM-generated plans are untrusted proposals until validated
3. Production-changing actions require policy-mandated approval
4. No silent mock substitution when credentials or APIs are unavailable
