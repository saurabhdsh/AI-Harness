"""Evaluation schemas — multi-dimension suites with custom thresholds."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class EvaluationCase(BaseModel):
    case_id: str
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] | None = None
    match_mode: str = "contains"  # exact | contains | keys | none
    # Per-case overrides
    dimensions: list[str] | None = None
    thresholds: dict[str, float] | None = None
    required_keys: list[str] | None = None
    required_nodes: list[str] | None = None
    max_latency_ms: float | None = None
    allow_pii: bool = False
    # Custom assertions: list of {type: contains|regex|json_equals|not_contains, value, field?}
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    weight: float = 1.0
    label: str | None = None


class EvaluationCreate(BaseModel):
    agent_id: UUID
    name: str = "quality-suite"
    cases: list[EvaluationCase] = Field(default_factory=list)
    # Suite-level dimensions & thresholds
    dimensions: list[str] = Field(
        default_factory=lambda: [
            "hallucination",
            "toxicity",
            "bias",
            "faithfulness",
            "relevance",
            "helpfulness",
            "pii_leakage",
            "schema_compliance",
            "task_completion",
            "latency",
            "security",
        ]
    )
    thresholds: dict[str, float] = Field(default_factory=dict)
    pass_score: float = 0.7  # aggregate gate
    max_latency_ms: float | None = 15000
    required_keys: list[str] = Field(default_factory=list)
    required_nodes: list[str] = Field(default_factory=list)
    use_llm_judge: bool = False
    llm_judge_url: str | None = None  # optional external; OpenAI env used if judge enabled
    skip_invoke: bool = False  # if true, score provided actual only (advanced)
    # When false (default), case passes if dimension aggregate meets pass_score.
    # When true, every selected dimension must individually clear its threshold.
    strict_dimensions: bool = False


class EvaluationResultOut(ORMModel):
    id: UUID
    case_id: str
    input_payload: dict[str, Any]
    expected: dict[str, Any] | None
    actual: dict[str, Any] | None
    score: float
    passed: bool
    metrics: dict[str, Any]
    judge_notes: str | None


class EvaluationRunOut(ORMModel):
    id: UUID
    tenant_id: UUID
    agent_id: UUID
    name: str
    status: str
    suite: dict[str, Any]
    use_llm_judge: bool
    aggregate_score: float | None
    summary: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    results: list[EvaluationResultOut] = Field(default_factory=list)
