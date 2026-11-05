from sqlalchemy import select

from materialops.errors import AppError
from materialops.models import Dept, User, Warehouse


def authenticate(session, employee_no):
    if not employee_no:
        raise AppError("AUTH_REQUIRED", "请通过 X-User 提供员工编号。")
    user = session.scalar(select(User).where(User.employee_no == employee_no))
    if user is None:
        raise AppError("AUTH_INVALID", "员工编号不存在。")
    return user


def subtree(session, dept_id):
    departments = session.scalars(select(Dept)).all()
    result = {dept_id}
    while True:
        expanded = result | {dept.id for dept in departments if dept.parent_id in result}
        if expanded == result:
            return result
        result = expanded


def department_scope(session, user):
    if user.role == "ADMIN":
        return {dept.id for dept in session.scalars(select(Dept)).all()}
    if user.role == "DISPATCHER":
        return subtree(session, user.dept_id)
    return {user.dept_id}


def warehouse_scope(session, user):
    depts = department_scope(session, user)
    return {row.id for row in session.scalars(select(Warehouse).where(Warehouse.dept_id.in_(depts))).all()}


def check_warehouse(session, user, warehouse_id):
    if warehouse_id not in warehouse_scope(session, user):
        raise AppError("NO_PERMISSION", "无权访问该仓库。")


def require_manager(user):
    if user.role not in {"ADMIN", "DISPATCHER"}:
        raise AppError("NO_PERMISSION", "该操作仅允许管理员或物资协调员。")

