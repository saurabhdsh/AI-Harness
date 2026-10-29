"""Mission control overview schemas."""

from typing import Any

from pydantic import BaseModel, Field


class MissionOverview(BaseModel):
    total_agents: int = 0
    by_lifecycle: dict[str, int] = Field(default_factory=dict)
    by_health: dict[str, int] = Field(default_factory=dict)
    by_evaluation: dict[str, int] = Field(default_factory=dict)
    recent_executions: int = 0
    failed_executions_24h: int = 0
    pending_approvals: int = 0
    total_cost_usd: float = 0.0
    # Agent 365–style hero metrics
    active_users_30d: int = 0
    agent_runtime_hours_30d: float = 0.0
    registry_sync: dict[str, Any] = Field(default_factory=dict)
    agents_without_owners: int = 0
    sessions_30d: int = 0
    exceptions_30d: int = 0
