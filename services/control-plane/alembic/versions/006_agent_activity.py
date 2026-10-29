"""Agent activity daily + collect_observability on connections.

Revision ID: 006_agent_activity
Revises: 005_agent_registry
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_agent_activity"
down_revision: Union[str, None] = "005_agent_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_connections",
        sa.Column("collect_observability", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "agent_activity_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exceptions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unique_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invocations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "agent_id", "day", "source", name="uq_activity_daily_agent_day_source"),
    )
    op.create_index("ix_agent_activity_daily_tenant_id", "agent_activity_daily", ["tenant_id"])
    op.create_index("ix_agent_activity_daily_agent_id", "agent_activity_daily", ["agent_id"])
    op.create_index("ix_agent_activity_daily_day", "agent_activity_daily", ["day"])
    op.create_index("ix_agent_activity_daily_source", "agent_activity_daily", ["source"])


def downgrade() -> None:
    op.drop_table("agent_activity_daily")
    op.drop_column("platform_connections", "collect_observability")
