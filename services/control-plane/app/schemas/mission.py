"""Mission control overview schemas."""

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
