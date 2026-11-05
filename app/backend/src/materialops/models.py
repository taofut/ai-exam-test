"""Only organizer-provided tables. Add candidate tables through new migrations."""
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from materialops.database import Base


class Dept(Base):
    __tablename__ = "t_dept"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("t_dept.id"))


class User(Base):
    __tablename__ = "t_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_no: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    dept_id: Mapped[int] = mapped_column(ForeignKey("t_dept.id"))


class Warehouse(Base):
    __tablename__ = "t_warehouse"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    dept_id: Mapped[int] = mapped_column(ForeignKey("t_dept.id"))


class Item(Base):
    __tablename__ = "t_item"
    __table_args__ = (CheckConstraint("reorder_point >= 0 AND target_stock >= reorder_point"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    item_no: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(20))
    reorder_point: Mapped[int] = mapped_column(Integer)
    target_stock: Mapped[int] = mapped_column(Integer)


class Inventory(Base):
    __tablename__ = "t_inventory"
    __table_args__ = (UniqueConstraint("warehouse_id", "item_id"), CheckConstraint("on_hand >= 0 AND version >= 0"))
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("t_warehouse.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("t_item.id"))
    on_hand: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=0)


class MaterialIssueOrder(Base):
    """Kit data structure only; no issue/return service is preimplemented."""
    __tablename__ = "t_material_issue_order"
    __table_args__ = (CheckConstraint("version >= 0", name="ck_issue_order_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(100), unique=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("t_warehouse.id"))
    issued_by_id: Mapped[int] = mapped_column(ForeignKey("t_user.id"))
    reason_text: Mapped[str] = mapped_column(Text, default="")
    issued_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class MaterialIssue(Base):
    """Provided data structure; issue/return business services remain candidate work."""
    __tablename__ = "t_material_issue"
    __table_args__ = (CheckConstraint("quantity > 0 AND version >= 0", name="ck_issue_quantity_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_no: Mapped[str] = mapped_column(String(100), unique=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("t_inventory.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    issued_by_id: Mapped[int] = mapped_column(ForeignKey("t_user.id"))
    issue_order_id: Mapped[int | None] = mapped_column(ForeignKey("t_material_issue_order.id"), nullable=True)
    reason_text: Mapped[str] = mapped_column(Text, default="")
    issued_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class StockMovement(Base):
    __tablename__ = "t_stock_movement"
    __table_args__ = (CheckConstraint("quantity > 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("t_inventory.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("t_item.id"))
    movement_type: Mapped[str] = mapped_column(String(30))
    business_no: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)
    before_on_hand: Mapped[int | None] = mapped_column(Integer)
    after_on_hand: Mapped[int | None] = mapped_column(Integer)
    actor_id: Mapped[int] = mapped_column(ForeignKey("t_user.id"))
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "t_audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("t_user.id"))
    action: Mapped[str] = mapped_column(String(100))
    parameters: Mapped[dict] = mapped_column(JSON)
    before_state: Mapped[dict] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class AICallLog(Base):
    __tablename__ = "t_ai_call_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("t_inventory.id"))
    inventory_version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int] = mapped_column(ForeignKey("t_user.id"))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    duration_ms: Mapped[int] = mapped_column(Integer)
    raw_output: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSON)
    original_suggestion: Mapped[dict | None] = mapped_column(JSON)
    final_suggestion: Mapped[dict | None] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(30), default="PENDING")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class FixtureHistory(Base):
    """Read-only public seed projection, never a successful candidate issue record."""
    __tablename__ = "t_fixture_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ExamClock(Base):
    __tablename__ = "t_exam_clock"
    id: Mapped[int] = mapped_column(primary_key=True)
    now: Mapped[object] = mapped_column(DateTime(timezone=True))

