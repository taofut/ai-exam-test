"""Keep knowledge and runtime persistence out of the organizer scaffold."""
from alembic import op


revision = "0003_candidate_owned_foundations"
down_revision = "0002_common_materials"
branch_labels = None
depends_on = None


def upgrade():
    # The table was part of an earlier starter revision.  Removing it on
    # upgrade ensures existing local databases follow the same boundary as a
    # fresh exam database.
    op.drop_table("t_kb_doc")


def downgrade():
    raise RuntimeError("Candidate-owned knowledge storage is intentionally not restorable by the scaffold.")
