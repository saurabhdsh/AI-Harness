"""Built-in multi-agent workflow definitions."""

from __future__ import annotations

BUILTIN_WORKFLOWS: list[dict] = [
    {
        "slug": "ad-delivery-pipeline",
        "name": "AD Delivery Pipeline",
        "domain": "AD",
        "version": "1.0.0",
        "description": (
            "Story authoring → human gate → tech design review. "
            "Maps to AD agents with optional skill injection."
        ),
        "tags": ["ad", "delivery", "hitl"],
        "sample_input": {
            "requirement": "Ops can pause a scheduled job from the console with audit trail."
        },
        "graph": {
            "nodes": [
                {
                    "id": "stories",
                    "type": "agent",
                    "label": "Author user stories",
                    "config": {
                        "domain": "AD",
                        "skill_slug": "ad-user-story-authoring",
                        "input_from": "input",
                    },
                },
                {
                    "id": "approve_stories",
                    "type": "hitl",
                    "label": "Approve stories",
                    "config": {
                        "message": "Review generated stories before design analysis.",
                        "context_keys": ["stories"],
                    },
                },
                {
                    "id": "design_review",
                    "type": "agent",
                    "label": "Tech design review",
                    "config": {
                        "domain": "AD",
                        "skill_slug": "ad-tech-design-review",
                        "input_map": {
                            "design": "requirement",
                            "stories_ref": "stories",
                        },
                    },
                },
            ],
            "edges": [
                {"from": "stories", "to": "approve_stories"},
                {"from": "approve_stories", "to": "design_review"},
            ],
        },
    },
    {
        "slug": "ams-incident-to-change",
        "name": "AMS Incident → Change",
        "domain": "AMS",
        "version": "1.0.0",
        "description": (
            "Incident RCA → change risk assessment → CAB human gate before next action."
        ),
        "tags": ["ams", "incident", "cab", "hitl"],
        "sample_input": {
            "incident": "Checkout p99 latency spike 18:00–18:40; Redis CPU 95%.",
            "symptoms": ["timeouts", "retry storms"],
        },
        "graph": {
            "nodes": [
                {
                    "id": "rca",
                    "type": "agent",
                    "label": "Incident RCA",
                    "config": {
                        "domain": "AMS",
                        "skill_slug": "ams-incident-rca",
                        "input_from": "input",
                    },
                },
                {
                    "id": "change_risk",
                    "type": "agent",
                    "label": "Change risk",
                    "config": {
                        "domain": "AMS",
                        "skill_slug": "ams-change-risk",
                        "input_map": {
                            "change": "incident",
                            "rca_summary": "rca",
                            "environment": "environment",
                        },
                    },
                },
                {
                    "id": "cab_gate",
                    "type": "hitl",
                    "label": "CAB approval",
                    "config": {
                        "message": "Approve recommended change controls before execution.",
                        "context_keys": ["rca", "change_risk"],
                    },
                },
            ],
            "edges": [
                {"from": "rca", "to": "change_risk"},
                {"from": "change_risk", "to": "cab_gate"},
            ],
        },
    },
    {
        "slug": "qe-quality-gate",
        "name": "QE Quality Gate",
        "domain": "QE",
        "version": "1.0.0",
        "description": "Test design → human review → defect triage handoff.",
        "tags": ["qe", "quality", "hitl"],
        "sample_input": {
            "feature": "Partial refund on multi-item orders with gift cards."
        },
        "graph": {
            "nodes": [
                {
                    "id": "test_design",
                    "type": "agent",
                    "label": "Design tests",
                    "config": {
                        "domain": "QE",
                        "skill_slug": "qe-test-design",
                        "input_from": "input",
                    },
                },
                {
                    "id": "review_suite",
                    "type": "hitl",
                    "label": "Approve test suite",
                    "config": {
                        "message": "Confirm P0 coverage before triage handoff.",
                        "context_keys": ["test_design"],
                    },
                },
                {
                    "id": "triage_ready",
                    "type": "transform",
                    "label": "Package for triage",
                    "config": {
                        "set": {
                            "handoff": "ready_for_triage",
                            "from_node": "test_design",
                        }
                    },
                },
            ],
            "edges": [
                {"from": "test_design", "to": "review_suite"},
                {"from": "review_suite", "to": "triage_ready"},
            ],
        },
    },
]
