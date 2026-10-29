"""Agent identity blueprint — reusable template for registry agents (Agent 365 mirror)."""

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AgentBlueprint(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """One blueprint can spawn many registry agents (identity registrations)."""

    __tablename__ = "agent_blueprints"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_agent_blueprints_tenant_slug"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False, default="generic_rest")
    framework: Mapped[str] = mapped_column(String(128), nullable=False, default="rest")
    default_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_risk_class: Mapped[str] = mapped_column(String(64), nullable=False, default="medium")
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    agents = relationship("Agent", back_populates="blueprint")
