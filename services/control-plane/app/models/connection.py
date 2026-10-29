"""Connected platform — credentials by reference; Sync populates the registry."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PlatformConnection(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """Agent 365–style connected platform. Manual Sync → registry inventory."""

    __tablename__ = "platform_connections"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Opaque reference into a secret store — NEVER store plaintext secrets here
    secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_agent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Agent 365–style: pull source-platform activity into KEEL Activity views
    collect_observability: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    agents = relationship("Agent", back_populates="connection")
