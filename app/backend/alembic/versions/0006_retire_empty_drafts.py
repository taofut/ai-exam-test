"""Retire the unused draft table without deleting existing business records."""
from alembic import op
import sqlalchemy as sa

revision = '0006_retire_empty_drafts'
down_revision = '0005_timed_kit_structure'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    table = 't_replenishment_draft'
    if not inspector.has_table(table):
        return
    # Legacy submissions may already contain plans or custom references.
    # Preserve them as legacy data; the timed scaffold no longer uses this table.
    if connection.execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar():
        return
    for name in inspector.get_table_names():
        if name != table and any(fk['referred_table'] == table for fk in inspector.get_foreign_keys(name)):
            return
    op.drop_table(table)


def downgrade():
    raise RuntimeError('The retired draft schema is not recreated; restore a database backup if required.')
