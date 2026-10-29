"""Agent 365–style registry: blueprints, unique external_id, connection sync.

Revision ID: 005_agent_registry
Revises: 004_workflows
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_agent_registry"
down_revision: Union[str, None] = "004_workflows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_blueprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("connector_type", sa.String(64), nullable=False),
        sa.Column("framework", sa.String(128), nullable=False),
        sa.Column("default_domain", sa.String(255), nullable=True),
        sa.Column("default_risk_class", sa.String(64), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_agent_blueprints_tenant_slug"),
    )
    op.create_index("ix_agent_blueprints_tenant_id", "agent_blueprints", ["tenant_id"])
    op.create_index("ix_agent_blueprints_slug", "agent_blueprints", ["slug"])

    op.add_column(
        "agents",
        sa.Column(
            "blueprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_blueprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_agents_blueprint_id", "agents", ["blueprint_id"])
    op.create_unique_constraint("uq_agents_tenant_external_id", "agents", ["tenant_id", "external_id"])

    op.add_column("platform_connections", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_connections", sa.Column("last_sync_status", sa.String(64), nullable=True))
    op.add_column("platform_connections", sa.Column("last_sync_error", sa.Text(), nullable=True))
    op.add_column(
        "platform_connections",
        sa.Column("synced_agent_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("platform_connections", "synced_agent_count")
    op.drop_column("platform_connections", "last_sync_error")
    op.drop_column("platform_connections", "last_sync_status")
    op.drop_column("platform_connections", "last_synced_at")
    op.drop_constraint("uq_agents_tenant_external_id", "agents", type_="unique")
    op.drop_index("ix_agents_blueprint_id", table_name="agents")
    op.drop_column("agents", "blueprint_id")
    op.drop_index("ix_agent_blueprints_slug", table_name="agent_blueprints")
    op.drop_index("ix_agent_blueprints_tenant_id", table_name="agent_blueprints")
    op.drop_table("agent_blueprints")
