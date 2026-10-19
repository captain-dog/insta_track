"""Rename kind 'followees' -> 'following' and index snapshot lookups.

Data is preserved; only the kind label changes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE snapshots SET kind = 'following' WHERE kind = 'followees'")
    op.create_index("ix_snapshots_target_kind_id", "snapshots", ["target", "kind", "id"])


def downgrade() -> None:
    op.drop_index("ix_snapshots_target_kind_id", table_name="snapshots")
    op.execute("UPDATE snapshots SET kind = 'followees' WHERE kind = 'following'")
