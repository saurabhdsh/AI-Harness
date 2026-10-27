"""Reliability Center — aggregates from real AgentExecution rows."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorClassBucket(BaseModel):
    class_id: str
    label: str
    count: int
    share: float  # 0–1 of failures
    sample_error: str | None = None


class AgentRisk(BaseModel):
    agent_id: UUID
    agent_name: str
    domain: str | None = None
    health_status: str
    total: int
    failed: int
    succeeded: int
    error_rate: float
    avg_latency_ms: float | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None


class TimelineBucket(BaseModel):
    t: str
    start: datetime
    ok: int
    fail: int
    total: int


class FailureEvent(BaseModel):
    execution_id: UUID
    agent_id: UUID
    agent_name: str
    status: str
    error: str | None
    error_class: str
    latency_ms: float | None
    created_at: datetime
    trace_id: str | None = None


class LatencyOutlier(BaseModel):
    execution_id: UUID
    agent_id: UUID
    agent_name: str
    status: str
    latency_ms: float
    created_at: datetime


class ReliabilityOverview(BaseModel):
    window_hours: int
    window_start: datetime
    generated_at: datetime
    total_executions: int
    succeeded: int
    failed: int
    running: int
    success_rate: float
    error_rate: float
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    max_latency_ms: float | None
    agents_invoked: int
    unhealthy_agents: int
    degraded_agents: int
    note: str = Field(
        default="All metrics derived from recorded agent executions — no synthetic SLOs."
    )
    error_classes: list[ErrorClassBucket] = Field(default_factory=list)
    agents_at_risk: list[AgentRisk] = Field(default_factory=list)
    timeline: list[TimelineBucket] = Field(default_factory=list)
    recent_failures: list[FailureEvent] = Field(default_factory=list)
    latency_outliers: list[LatencyOutlier] = Field(default_factory=list)
    # Raw hint for UI debugging / export
    meta: dict[str, Any] = Field(default_factory=dict)
