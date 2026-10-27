"""Built-in enterprise skill definitions (seeded per tenant)."""

from __future__ import annotations

BUILTIN_SKILLS: list[dict] = [
    {
        "slug": "ad-architecture-analysis",
        "name": "Architecture Analysis",
        "domain": "AD",
        "version": "1.0.0",
        "description": "Assess system architecture for risks, trade-offs, and improvement options.",
        "instructions": (
            "You are an Application Development architecture analyst. "
            "Given a system/context description, produce: (1) current-state summary, "
            "(2) risks ranked by severity, (3) recommended options with trade-offs, "
            "(4) a short decision checklist for stakeholders. Be concrete; avoid generic advice."
        ),
        "input_schema": {
            "type": "object",
            "required": ["context"],
            "properties": {
                "context": {"type": "string", "description": "Architecture / system context"},
                "constraints": {"type": "array", "items": {"type": "string"}},
            },
        },
        "output_schema": {
            "summary": "string",
            "risks": [{"title": "string", "severity": "high|medium|low", "mitigation": "string"}],
            "options": [{"name": "string", "pros": ["string"], "cons": ["string"]}],
            "checklist": ["string"],
        },
        "eval_suite": {
            "cases": [
                {
                    "name": "monolith-to-services",
                    "input": {
                        "context": "Legacy Java monolith, 2M LOC, shared DB, peak traffic 3x baseline at month-end."
                    },
                    "expect_contains": ["risk", "option"],
                }
            ]
        },
        "risk_class": "medium",
        "tags": ["architecture", "ad", "design"],
        "sample_input": {
            "context": "Payment API behind API gateway; Redis cache; Postgres; nightly batch reconcile."
        },
    },
    {
        "slug": "ad-user-story-authoring",
        "name": "User Story Authoring",
        "domain": "AD",
        "version": "1.0.0",
        "description": "Turn requirements into INVEST-quality user stories with acceptance criteria.",
        "instructions": (
            "You are an AD product analyst. Convert the requirement into user stories. "
            "Each story: title, as-a/I-want/so-that, acceptance criteria (Given/When/Then), "
            "and a rough size (S/M/L). Prefer small, testable slices."
        ),
        "input_schema": {
            "type": "object",
            "required": ["requirement"],
            "properties": {
                "requirement": {"type": "string"},
                "persona": {"type": "string"},
            },
        },
        "output_schema": {
            "stories": [
                {
                    "title": "string",
                    "narrative": "string",
                    "acceptance_criteria": ["string"],
                    "size": "S|M|L",
                }
            ]
        },
        "eval_suite": {
            "cases": [
                {
                    "name": "password-reset",
                    "input": {"requirement": "Users need to reset forgotten passwords via email OTP."},
                    "expect_contains": ["Given", "When"],
                }
            ]
        },
        "risk_class": "low",
        "tags": ["agile", "ad", "requirements"],
        "sample_input": {"requirement": "Allow ops to pause a scheduled job from the console."},
    },
    {
        "slug": "ad-tech-design-review",
        "name": "Tech Design Review",
        "domain": "AD",
        "version": "1.0.0",
        "description": "Structured review of a technical design for gaps and production readiness.",
        "instructions": (
            "You are a senior AD tech lead reviewing a design. Cover: correctness, failure modes, "
            "observability, security, data, rollout/rollback, and open questions. "
            "Flag blockers vs nice-to-haves."
        ),
        "input_schema": {
            "type": "object",
            "required": ["design"],
            "properties": {"design": {"type": "string"}, "service": {"type": "string"}},
        },
        "output_schema": {
            "verdict": "approve|approve_with_comments|request_changes",
            "blockers": ["string"],
            "comments": ["string"],
            "open_questions": ["string"],
        },
        "eval_suite": {
            "cases": [
                {
                    "name": "missing-rollback",
                    "input": {
                        "design": "Blue-green deploy of payments; no stated rollback; schema migration in-place."
                    },
                    "expect_contains": ["rollback", "blocker"],
                }
            ]
        },
        "risk_class": "high",
        "tags": ["design-review", "ad"],
        "sample_input": {
            "design": "Add outbox table for order events; worker publishes to Kafka; consumers idempotent by order_id."
        },
    },
    {
        "slug": "ad-code-impact-analysis",
        "name": "Code Impact Analysis",
        "domain": "AD",
        "version": "1.0.0",
        "description": "Estimate blast radius and test focus for a proposed change.",
        "instructions": (
            "You are an AD impact analyst. Given a change description, list likely affected modules, "
            "downstream consumers, regression risk areas, and a focused test plan."
        ),
        "input_schema": {
            "type": "object",
            "required": ["change"],
            "properties": {"change": {"type": "string"}, "repo_hints": {"type": "array"}},
        },
        "output_schema": {
            "affected": ["string"],
            "downstream": ["string"],
            "risks": ["string"],
            "test_plan": ["string"],
        },
        "eval_suite": {"cases": []},
        "risk_class": "medium",
        "tags": ["impact", "ad", "change"],
        "sample_input": {"change": "Rename Order.status enum value PENDING to AWAITING_PAYMENT."},
    },
    {
        "slug": "ams-incident-rca",
        "name": "Incident RCA",
        "domain": "AMS",
        "version": "1.0.0",
        "description": "Structured root-cause analysis for production incidents.",
        "instructions": (
            "You are an AMS incident commander assistant. Produce a concise RCA: timeline, "
            "impact, proximate cause, contributing factors, detection gaps, and corrective actions "
            "(immediate + preventive). Separate facts from hypotheses."
        ),
        "input_schema": {
            "type": "object",
            "required": ["incident"],
            "properties": {
                "incident": {"type": "string"},
                "symptoms": {"type": "array", "items": {"type": "string"}},
                "timeline": {"type": "array", "items": {"type": "string"}},
            },
        },
        "output_schema": {
            "summary": "string",
            "impact": "string",
            "root_cause": "string",
            "contributing_factors": ["string"],
            "actions": [{"type": "immediate|preventive", "action": "string", "owner": "string"}],
        },
        "eval_suite": {
            "cases": [
                {
                    "name": "cache-stampede",
                    "input": {
                        "incident": "Checkout p99 latency spike 18:00–18:40; Redis CPU 95%.",
                        "symptoms": ["timeouts", "retry storms"],
                    },
                    "expect_contains": ["root", "action"],
                }
            ]
        },
        "risk_class": "high",
        "tags": ["incident", "ams", "rca"],
        "sample_input": {
            "incident": "API 5xx surge after deploy; rolled back in 12 minutes.",
            "symptoms": ["NullPointer in PaymentService"],
        },
    },
    {
        "slug": "ams-change-risk",
        "name": "Change Risk Assessment",
        "domain": "AMS",
        "version": "1.0.0",
        "description": "Score change risk and recommend CAB / freeze / go-live controls.",
        "instructions": (
            "You are an AMS change manager. Score risk (low/medium/high/critical), cite drivers, "
            "recommend controls (canary, freeze window, rollback plan, CAB), and list go/no-go checks."
        ),
        "input_schema": {
            "type": "object",
            "required": ["change"],
            "properties": {
                "change": {"type": "string"},
                "environment": {"type": "string"},
                "window": {"type": "string"},
            },
        },
        "output_schema": {
            "risk": "low|medium|high|critical",
            "drivers": ["string"],
            "controls": ["string"],
            "go_nogo": ["string"],
        },
        "eval_suite": {"cases": []},
        "risk_class": "high",
        "tags": ["change", "ams", "cab"],
        "sample_input": {
            "change": "DB index rebuild on orders during business hours",
            "environment": "prod",
        },
    },
    {
        "slug": "qe-test-design",
        "name": "Test Design",
        "domain": "QE",
        "version": "1.0.0",
        "description": "Design risk-based test suites from requirements or change notes.",
        "instructions": (
            "You are a QE test designer. Produce: scope, risk matrix, test cases "
            "(positive/negative/edge), data needs, and automation candidates. Prioritize by risk."
        ),
        "input_schema": {
            "type": "object",
            "required": ["feature"],
            "properties": {
                "feature": {"type": "string"},
                "risks": {"type": "array", "items": {"type": "string"}},
            },
        },
        "output_schema": {
            "scope": "string",
            "cases": [{"id": "string", "title": "string", "type": "string", "priority": "P0|P1|P2"}],
            "data_needs": ["string"],
            "automation": ["string"],
        },
        "eval_suite": {
            "cases": [
                {
                    "name": "otp-login",
                    "input": {"feature": "Email OTP login with 5-minute expiry and 3 attempts."},
                    "expect_contains": ["P0", "negative"],
                }
            ]
        },
        "risk_class": "medium",
        "tags": ["qe", "test-design"],
        "sample_input": {"feature": "Partial refund on multi-item orders."},
    },
    {
        "slug": "qe-defect-triage",
        "name": "Defect Triage",
        "domain": "QE",
        "version": "1.0.0",
        "description": "Triage defects for severity, priority, and next action.",
        "instructions": (
            "You are a QE triage lead. Classify severity/priority, suggest owner team, "
            "reproduce steps quality score, and recommend next action (fix-now / defer / need-info)."
        ),
        "input_schema": {
            "type": "object",
            "required": ["defect"],
            "properties": {
                "defect": {"type": "string"},
                "environment": {"type": "string"},
            },
        },
        "output_schema": {
            "severity": "S1|S2|S3|S4",
            "priority": "P0|P1|P2|P3",
            "owner_hint": "string",
            "next_action": "string",
            "rationale": "string",
        },
        "eval_suite": {"cases": []},
        "risk_class": "low",
        "tags": ["qe", "triage", "defect"],
        "sample_input": {
            "defect": "Checkout button disabled on Safari 17 when cart has gift card + coupon.",
            "environment": "staging",
        },
    },
]
