"""Agent and AgentVersion models — registry inventory (Agent 365 registration)."""

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Agent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """Registry inventory record. Identity key = (tenant_id, external_id)."""

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_agents_tenant_external_id"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(128), nullable=False, default="generic")
    framework: Mapped[str] = mapped_column(String(128), nullable=False, default="rest")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False, default="dev")
    lifecycle_state: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="draft",
        index=True,
    )
    risk_class: Mapped[str] = mapped_column(String(64), nullable=False, default="medium")
    health_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    evaluation_status: Mapped[str] = mapped_column(String(64), nullable=False, default="none")
    connection_id: Mapped[object | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    blueprint_id: Mapped[object | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_blueprints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoke_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    tenant = relationship("Tenant", back_populates="agents")
    connection = relationship("PlatformConnection", back_populates="agents")
    blueprint = relationship("AgentBlueprint", back_populates="agents")
    versions = relationship(
        "AgentVersion",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentVersion.created_at.desc()",
    )
    executions = relationship(
        "AgentExecution",
        back_populates="agent",
        cascade="all, delete-orphan",
    )


class AgentVersion(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "agent_versions"

    agent_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)

    agent = relationship("Agent", back_populates="versions")
