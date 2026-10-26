# Data Model

PostgreSQL is the system of record for transactional control-plane data.

## Core entities (implemented)

| Entity | Purpose |
|--------|---------|
| Tenant | Isolation boundary |
| User | Authenticated actors |
| PlatformConnection | Connector config + `secret_ref` + capability JSON |
| Agent | Control-plane identity + native external_id |
| AgentVersion | Version history |
| AgentExecution | Invocation records |
| AgentTrace | Span waterfall per execution |
| EvaluationRun / EvaluationResult | Evaluation evidence |
| AuditEvent | Immutable control-plane audit |
| ApprovalRequest | HITL approvals |
| Policy | Policy catalog (CRUD pending) |
| CostRecord / Budget | FinOps attribution (estimated rates labeled) |

## Identifiers

- UUID primary keys
- Tenant scoping on all operational tables
- Stable `external_id` for de-duplicating discovery

## Analytical / object stores (planned)

- ClickHouse for high-volume telemetry
- S3-compatible storage for evaluation artifacts

## Migrations

- Alembic: `services/control-plane/alembic/versions/001_initial_schema.py`
- Demo fallback: `AUTO_CREATE_TABLES=true` uses SQLAlchemy `create_all`
