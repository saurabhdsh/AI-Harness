"""Evaluation run and result models."""

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy import JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EvaluationRun(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "evaluation_runs"

    agent_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending", index=True)
    suite: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    use_llm_judge: Mapped[bool] = mapped_column(default=False)
    aggregate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    results = relationship(
        "EvaluationResult",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EvaluationResult(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "evaluation_results"

    run_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actual: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    passed: Mapped[bool] = mapped_column(default=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    judge_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    run = relationship("EvaluationRun", back_populates="results")
