from materialops.errors import AppError


def object_body(body, *, empty=False):
    if body is None and empty:
        return {}
    if not isinstance(body, dict):
        raise AppError("VALIDATION_ERROR", "请求体须为 JSON 对象。")
    return body


def integer(body, field, *, quantity=False, minimum=0):
    if field not in body:
        raise AppError("VALIDATION_ERROR", f"缺少字段 {field}。")
    value = body[field]
    if type(value) is not int or value < minimum:
        raise AppError("QUANTITY_INVALID" if quantity else "VALIDATION_ERROR", f"{field} 须为{'正' if minimum else '非负'}整数。")
    return value


def nonblank(body, field, *, limit=None):
    value = body.get(field)
    if not isinstance(value, str) or not value.strip() or limit and len(value) > limit:
        raise AppError("VALIDATION_ERROR", f"{field} 须为非空字符串。")
    return value


def query_args(body, allowed):
    object_body(body)
    if set(body) - set(allowed):
        raise AppError("QUERY_ARGUMENT_INVALID", "查询只接受公开白名单参数。")
    for key in {"deptId", "warehouseId", "itemId"} & set(body):
        if type(body[key]) is not int or body[key] <= 0:
            raise AppError("QUERY_ARGUMENT_INVALID", f"{key} 须为实体 ID。")
    if "belowReorderPoint" in body and type(body["belowReorderPoint"]) is not bool:
        raise AppError("QUERY_ARGUMENT_INVALID", "belowReorderPoint 须为布尔值。")
    if "period" in body and (not isinstance(body["period"], str) or body["period"] not in {"TODAY"}):
        raise AppError("QUERY_ARGUMENT_INVALID", "period 无效。")
    if "groupBy" in body and (not isinstance(body["groupBy"], str) or body["groupBy"] not in {"ITEM"}):
        raise AppError("QUERY_ARGUMENT_INVALID", "groupBy 无效。")
    return body

