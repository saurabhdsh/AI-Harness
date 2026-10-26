"""Release trains and promotions.

Revision ID: 002_releases
Revises: 001_initial
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_releases"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "release_trains",
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
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_release_trains_tenant_id", "release_trains", ["tenant_id"])
    op.create_index("ix_release_trains_slug", "release_trains", ["slug"])
    op.create_index("ix_release_trains_name", "release_trains", ["name"])

    op.create_table(
        "promotions",
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
        sa.Column(
            "train_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("release_trains.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("from_env", sa.String(64), nullable=False),
        sa.Column("to_env", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="gating"),
        sa.Column("gates", sa.JSON(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "approval_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_promotions_tenant_id", "promotions", ["tenant_id"])
    op.create_index("ix_promotions_agent_id", "promotions", ["agent_id"])
    op.create_index("ix_promotions_train_id", "promotions", ["train_id"])
    op.create_index("ix_promotions_status", "promotions", ["status"])
    op.create_index("ix_promotions_approval_id", "promotions", ["approval_id"])


def downgrade() -> None:
    op.drop_table("promotions")
    op.drop_table("release_trains")
