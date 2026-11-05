"""Provide kit parent/line structure; candidates implement atomic business writes."""
from alembic import op
import sqlalchemy as sa

revision = '0005_timed_kit_structure'
down_revision = '0004_timed_issue_table'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('t_material_issue_order'):
        op.create_table(
            't_material_issue_order',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('order_no', sa.String(100), nullable=False, unique=True),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('t_warehouse.id'), nullable=False),
            sa.Column('issued_by_id', sa.Integer(), sa.ForeignKey('t_user.id'), nullable=False),
            sa.Column('reason_text', sa.Text(), nullable=False, server_default=''),
            sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('returned_at', sa.DateTime(timezone=True)),
            sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
            sa.CheckConstraint('version >= 0', name='ck_issue_order_version'),
        )
    columns = {c['name'] for c in inspector.get_columns('t_material_issue')}
    # Preserve a pre-existing candidate alias rather than add a competing link.
    if not {'issue_order_id', 'issueOrderId'} & columns:
        if op.get_bind().dialect.name == 'sqlite':
            # SQLite supports a nullable REFERENCES column in ADD COLUMN, but
            # Alembic otherwise emits an unsupported separate ADD CONSTRAINT.
            op.execute('ALTER TABLE t_material_issue ADD COLUMN issue_order_id INTEGER REFERENCES t_material_issue_order(id)')
        else:
            op.add_column('t_material_issue', sa.Column(
                'issue_order_id', sa.Integer(),
                sa.ForeignKey('t_material_issue_order.id'), nullable=True,
            ))


def downgrade():
    # Existing candidate schemas/records may predate this organizer revision.
    # Keep business data on downgrade; never silently drop parent/line records.
    pass
