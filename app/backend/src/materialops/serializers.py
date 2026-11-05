from materialops.models import Dept


def user_json(session, user):
    return {"id": user.id, "employeeNo": user.employee_no, "name": user.name,
            "role": user.role, "deptId": user.dept_id, "deptName": session.get(Dept, user.dept_id).name}


def warehouse_json(row):
    return {"id": row.id, "name": row.name, "deptId": row.dept_id}


def item_json(row):
    return {"id": row.id, "itemNo": row.item_no, "name": row.name, "unit": row.unit,
            "reorderPoint": row.reorder_point, "targetStock": row.target_stock}

