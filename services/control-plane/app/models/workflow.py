"""Workflow definitions, runs, and step executions."""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowDefinition(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflow_definitions"

    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, default="AD", index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    # { nodes: [...], edges: [...] }
    graph: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sample_input: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    runs = relationship("WorkflowRun", back_populates="definition")


class WorkflowRun(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflow_runs"

    definition_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="pending", index=True
    )
    # pending | running | awaiting_approval | succeeded | failed | cancelled
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    agent_bindings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    current_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by: Mapped[object | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pending_approval_id: Mapped[object | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    definition = relationship("WorkflowDefinition", back_populates="runs")
    steps = relationship(
        "WorkflowStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.seq",
    )


class WorkflowStep(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflow_steps"

    run_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="pending", index=True
    )
    # pending | running | awaiting_approval | succeeded | failed | skipped | rejected
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_id: Mapped[object | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    execution_id: Mapped[object | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_id: Mapped[object | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    run = relationship("WorkflowRun", back_populates="steps")
