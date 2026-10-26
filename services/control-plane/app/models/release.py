"""Release trains and promotions — gated environment moves."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ReleaseTrain(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """Named promotion path (e.g. Standard: dev → staging → prod)."""

    __tablename__ = "release_trains"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ordered stages: [{env, gates: [evaluation|approval], require_for_risk: [...]}]
    stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class Promotion(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """One gated promote of an agent from_env → to_env."""

    __tablename__ = "promotions"

    agent_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    train_id: Mapped[object | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("release_trains.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    from_env: Mapped[str] = mapped_column(String(64), nullable=False)
    to_env: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="gating",
        index=True,
    )
    # [{id, type, required, status: pending|passed|failed|skipped, detail}]
    gates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[object | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_id: Mapped[object | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
