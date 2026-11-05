"""Provide single-material storage for the timed exam, without write services."""
from alembic import op
import sqlalchemy as sa

revision = '0004_timed_issue_table'
down_revision = '0003_candidate_owned_foundations'
branch_labels = None
depends_on = None


def upgrade():
    # Existing candidate implementations are not overwritten or reset.
    if sa.inspect(op.get_bind()).has_table('t_material_issue'):
        return
    op.create_table(
        't_material_issue',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('issue_no', sa.String(100), nullable=False, unique=True),
        sa.Column('inventory_id', sa.Integer(), sa.ForeignKey('t_inventory.id'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('issued_by_id', sa.Integer(), sa.ForeignKey('t_user.id'), nullable=False),
        sa.Column('reason_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('returned_at', sa.DateTime(timezone=True)),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('quantity > 0 AND version >= 0', name='ck_issue_quantity_version'),
    )


def downgrade():
    # The table may predate this revision and contains user business records.
    # A backwards schema operation must not silently delete it.
    pass
