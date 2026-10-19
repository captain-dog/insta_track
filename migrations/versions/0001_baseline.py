"""Baseline schema: snapshots and snapshot_users.

Matches the schema created by the original single-file script, so an existing
database is adopted as-is (tables are only created when missing).

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "snapshots" not in existing_tables:
        op.create_table(
            "snapshots",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("taken_at", sa.DateTime, nullable=False),
            sa.Column("target", sa.String, nullable=False),
            sa.Column("kind", sa.String, nullable=False),
            sqlite_autoincrement=True,
        )
    if "snapshot_users" not in existing_tables:
        op.create_table(
            "snapshot_users",
            sa.Column("snapshot_id", sa.Integer, sa.ForeignKey("snapshots.id"), primary_key=True),
            sa.Column("user_id", sa.BigInteger, primary_key=True),
            sa.Column("username", sa.String, nullable=False),
        )


def downgrade() -> None:
    op.drop_table("snapshot_users")
    op.drop_table("snapshots")
