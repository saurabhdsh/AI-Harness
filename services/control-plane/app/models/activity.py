"""Agent activity snapshots — Agent 365–style sessions / runtime / exceptions."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AgentActivityDaily(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """Daily activity rollup per agent (KEEL invokes + federated platform telemetry)."""

    __tablename__ = "agent_activity_daily"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "agent_id", "day", "source", name="uq_activity_daily_agent_day_source"
        ),
    )

    agent_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="keel", index=True
    )  # keel | bedrock | copilot_studio | otel | …
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exceptions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unique_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invocations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
