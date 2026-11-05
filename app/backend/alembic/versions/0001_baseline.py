"""Organizer tables only; T1 issue/idempotency and T3 transfer tables are absent."""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("t_dept", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("parent_id", sa.Integer(), sa.ForeignKey("t_dept.id")))
    op.create_table("t_user", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("employee_no", sa.String(100), unique=True, nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("dept_id", sa.Integer(), sa.ForeignKey("t_dept.id"), nullable=False))
    op.create_table("t_warehouse", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("dept_id", sa.Integer(), sa.ForeignKey("t_dept.id"), nullable=False), sa.Column("industry", sa.String(30), nullable=False))
    op.create_table("t_item", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("item_no", sa.String(100), unique=True, nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("unit", sa.String(20), nullable=False), sa.Column("reorder_point", sa.Integer(), nullable=False), sa.Column("target_stock", sa.Integer(), nullable=False), sa.Column("industry", sa.String(30), nullable=False), sa.CheckConstraint("reorder_point >= 0 AND target_stock >= reorder_point"))
    op.create_table("t_inventory", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("t_warehouse.id"), nullable=False), sa.Column("item_id", sa.Integer(), sa.ForeignKey("t_item.id"), nullable=False), sa.Column("on_hand", sa.Integer(), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.UniqueConstraint("warehouse_id", "item_id"), sa.CheckConstraint("on_hand >= 0 AND version >= 0"))
    op.create_table("t_stock_movement", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("inventory_id", sa.Integer(), sa.ForeignKey("t_inventory.id"), nullable=False), sa.Column("item_id", sa.Integer(), sa.ForeignKey("t_item.id"), nullable=False), sa.Column("movement_type", sa.String(30), nullable=False), sa.Column("business_no", sa.String(100), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("before_on_hand", sa.Integer()), sa.Column("after_on_hand", sa.Integer()), sa.Column("actor_id", sa.Integer(), sa.ForeignKey("t_user.id"), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("quantity > 0"))
    op.create_table("t_audit_log", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("actor_id", sa.Integer(), sa.ForeignKey("t_user.id"), nullable=False), sa.Column("action", sa.String(100), nullable=False), sa.Column("parameters", sa.JSON(), nullable=False), sa.Column("before_state", sa.JSON(), nullable=False), sa.Column("after_state", sa.JSON(), nullable=False), sa.Column("result", sa.String(30), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("t_ai_call_log", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("inventory_id", sa.Integer(), sa.ForeignKey("t_inventory.id"), nullable=False), sa.Column("inventory_version", sa.Integer(), nullable=False), sa.Column("actor_id", sa.Integer(), sa.ForeignKey("t_user.id"), nullable=False), sa.Column("model", sa.String(200), nullable=False), sa.Column("prompt_version", sa.String(100), nullable=False), sa.Column("duration_ms", sa.Integer(), nullable=False), sa.Column("raw_output", sa.Text()), sa.Column("input_tokens", sa.Integer()), sa.Column("output_tokens", sa.Integer()), sa.Column("failure_reason", sa.Text()), sa.Column("context", sa.JSON()), sa.Column("original_suggestion", sa.JSON()), sa.Column("final_suggestion", sa.JSON()), sa.Column("decision", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("t_replenishment_draft", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("inventory_id", sa.Integer(), sa.ForeignKey("t_inventory.id"), nullable=False), sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("t_warehouse.id"), nullable=False), sa.Column("item_id", sa.Integer(), sa.ForeignKey("t_item.id"), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("source_call_id", sa.Integer(), sa.ForeignKey("t_ai_call_log.id"), unique=True, nullable=False), sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("t_user.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.CheckConstraint("quantity > 0"))
    op.create_table("t_kb_doc", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(300), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("dept_id", sa.Integer(), sa.ForeignKey("t_dept.id")))
    op.create_table("t_fixture_history", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("payload", sa.JSON(), nullable=False))
    op.create_table("t_exam_clock", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("now", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    for table in ["t_exam_clock", "t_fixture_history", "t_kb_doc", "t_replenishment_draft", "t_ai_call_log", "t_audit_log", "t_stock_movement", "t_inventory", "t_item", "t_warehouse", "t_user", "t_dept"]:
        op.drop_table(table)

