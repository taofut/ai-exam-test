"""Remove legacy classification metadata from the shared material catalog.

Revision ID: 0002_common_materials
Revises: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_common_materials"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    # Direct DROP COLUMN keeps existing inbound SQLite foreign keys intact.
    op.drop_column("t_warehouse", "industry")
    op.drop_column("t_item", "industry")


def downgrade():
    # Removed classification values cannot be reconstructed from stock records.
    op.add_column("t_warehouse", sa.Column("industry", sa.String(30), nullable=False, server_default="GENERIC"))
    op.add_column("t_item", sa.Column("industry", sa.String(30), nullable=False, server_default="GENERIC"))
