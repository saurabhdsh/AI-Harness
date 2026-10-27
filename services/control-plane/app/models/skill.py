"""Enterprise reusable skills + agent attachments."""

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Skill(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """Versioned enterprise skill from the catalog (tenant-scoped copy)."""

    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", "version", name="uq_skill_slug_ver"),)

    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # AD | AMS | QE
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # System / skill instructions injected at invoke time
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Expected I/O shapes (JSON Schema-ish or freeform dicts)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Suggested Evaluation Lab cases
    eval_suite: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_class: Mapped[str] = mapped_column(String(64), nullable=False, default="medium")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sample_input: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AgentSkill(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """Attachment of a catalog skill to an onboarded agent."""

    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill"),
    )

    agent_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attached_by: Mapped[object | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Optional per-attachment overrides (e.g. project context)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
