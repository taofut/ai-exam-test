from contextlib import asynccontextmanager
import logging
from typing import Any

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import MetaData, select
from starlette.exceptions import HTTPException

from materialops.api.validation import integer, nonblank, object_body, query_args
from materialops.api.advice import router as advice_router
from materialops.api.issue_orders import router as issue_orders_router
from materialops.config import Settings, settings
from materialops.database import Database
from materialops.errors import AppError, pending
from materialops.models import ExamClock, Inventory, Item, User, Warehouse
from materialops.seed import default_dataset, reset_dataset
from materialops.serializers import item_json, user_json, warehouse_json
from materialops.services.access import authenticate, check_warehouse, require_manager, warehouse_scope
from materialops.services.clock import iso, now, stored_utc, utc
from materialops.services.history import read_history
from materialops.services.issue import issue_material, return_material
from materialops.services.queries import get_inventory, get_issue, inventory_json, issue_stats, list_inventories, visible_history


def create_app(configuration: Settings | None = None):
    configuration = configuration or settings
    database = Database(configuration.database_url)

    @asynccontextmanager
    async def lifespan(app):
        database.migrate()
        yield
        database.engine.dispose()

    app = FastAPI(title="MaterialOps Exam Starter", lifespan=lifespan)
    app.state.settings = configuration
    app.state.database = database
    app.include_router(issue_orders_router)
    app.include_router(advice_router)
    app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in configuration.cors_origins.split(",")], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(AppError)
    async def application_error(request: Request, error):
        content = {"code": error.code, "message": error.message}
        kit_path = '/api/material-issue-orders'
        if error.details is not None and (request.url.path == kit_path or request.url.path.startswith(kit_path + '/')):
            content['details'] = error.details
        return JSONResponse(status_code=error.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": "请求结构不符合接口要求。"})

    @app.exception_handler(HTTPException)
    async def invalid_http_request(_, error):
        # No endpoint/method error codes are specified. Treat an unsupported
        # HTTP request as a structural validation failure using the public code.
        return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "message": "请求路径或 HTTP 方法不符合接口要求。"})

    @app.exception_handler(Exception)
    async def internal_error(_, error):
        logging.getLogger("materialops").error("Unhandled backend error: %s", type(error).__name__)
        return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "服务处理失败，请检查服务日志。"})

    def dev_allowed():
        if not configuration.allow_exam_reset:
            raise AppError("NO_PERMISSION", "开发夹具已关闭，请在独立考试库启用 ALLOW_EXAM_RESET。")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/session/users")
    def session_users():
        with database.sessions() as session:
            return [user_json(session, user) for user in session.scalars(select(User).order_by(User.id)).all()]

    @app.get("/api/session/me")
    def session_me(x_user: str | None = Header(None)):
        with database.sessions() as session:
            return user_json(session, authenticate(session, x_user))

    @app.get("/api/warehouses")
    def warehouses(x_user: str | None = Header(None)):
        with database.sessions() as session:
            user = authenticate(session, x_user)
            statement = select(Warehouse).join(Inventory).where(Warehouse.id.in_(warehouse_scope(session, user))).distinct().order_by(Warehouse.id)
            return {"items": [warehouse_json(row) for row in session.scalars(statement).all()]}

    @app.get("/api/items")
    def items(x_user: str | None = Header(None)):
        with database.sessions() as session:
            user = authenticate(session, x_user)
            statement = select(Item).join(Inventory).where(Inventory.warehouse_id.in_(warehouse_scope(session, user))).distinct().order_by(Item.id)
            return {"items": [item_json(row) for row in session.scalars(statement).all()]}

    @app.get("/api/inventories")
    def inventories(deptId: int | None = Query(None, gt=0), warehouseId: int | None = Query(None, gt=0), itemId: int | None = Query(None, gt=0), belowReorderPoint: bool | None = None, x_user: str | None = Header(None)):
        with database.sessions() as session:
            return list_inventories(session, authenticate(session, x_user), deptId=deptId, warehouseId=warehouseId, itemId=itemId, belowReorderPoint=belowReorderPoint)

    @app.get("/api/inventories/{inventory_id}")
    def inventory_detail(inventory_id: int, x_user: str | None = Header(None)):
        with database.sessions() as session:
            user = authenticate(session, x_user)
            return inventory_json(session, get_inventory(session, user, inventory_id), user)

    @app.get("/api/material-issues")
    def material_issues(warehouseId: int | None = Query(None, gt=0), itemId: int | None = Query(None, gt=0), status: str | None = None, mine: bool = False, x_user: str | None = Header(None)):
        if status is not None and status not in {"ISSUED", "RETURNED"}:
            raise AppError("QUERY_ARGUMENT_INVALID", "status 无效。")
        with database.sessions() as session:
            return {"items": visible_history(session, authenticate(session, x_user), warehouseId=warehouseId, itemId=itemId, status=status, mine=mine)}

    # Register stats before the entity route to prevent interpreting 'stats' as an ID.
    @app.get("/api/material-issues/stats")
    def material_stats(warehouseId: int | None = Query(None, gt=0), itemId: int | None = Query(None, gt=0), period: str = "TODAY", groupBy: str = "ITEM", x_user: str | None = Header(None)):
        query_args({"period": period, "groupBy": groupBy}, {"period", "groupBy"})
        with database.sessions() as session:
            return issue_stats(session, authenticate(session, x_user), configuration.exam_now, warehouseId=warehouseId, itemId=itemId, period=period, groupBy=groupBy)

    @app.get("/api/material-issues/{issue_id}")
    def issue_detail(issue_id: int, x_user: str | None = Header(None)):
        with database.sessions() as session:
            return get_issue(session, authenticate(session, x_user), issue_id)

    @app.post("/api/tools/{tool_name}")
    def tools(tool_name: str, body: Any = Body(None), x_user: str | None = Header(None)):
        with database.sessions() as session:
            user = authenticate(session, x_user)
            if tool_name == "inventory_query":
                params = query_args(body, {"deptId", "warehouseId", "itemId", "belowReorderPoint"})
                return list_inventories(session, user, **params)
            if tool_name == "issue_stats":
                params = query_args(body, {"warehouseId", "itemId", "period", "groupBy"})
                if "period" not in params:
                    raise AppError("QUERY_ARGUMENT_INVALID", "统计工具须提供 period。")
                return issue_stats(session, user, configuration.exam_now, **params)
            raise AppError("QUERY_ARGUMENT_INVALID", "只接受公开查询工具。")

    @app.post("/api/inventories/{inventory_id}/issue")
    def issue(inventory_id: int, body: Any = Body(None), x_user: str | None = Header(None)):
        with database.sessions() as session:
            user = authenticate(session, x_user)
            get_inventory(session, user, inventory_id)
            if user.role == "REPORTER":
                raise AppError("NO_PERMISSION", "申请查看人不能领用物资。")
            body = object_body(body)
            integer(body, "quantity", quantity=True, minimum=1)
            integer(body, "version")
            if "requestId" in body:
                nonblank(body, "requestId", limit=64)
            if not isinstance(body.get("reasonText", ""), str) or len(body.get("reasonText", "")) > 500:
                raise AppError("VALIDATION_ERROR", "reasonText 须为不超过 500 字符的字符串。")
        return issue_material(database, configuration.exam_now, user, inventory_id,
                              body["quantity"], body["version"], body.get("reasonText", ""))

    @app.post("/api/material-issues/{issue_id}/return")
    def return_issue(issue_id: int, body: Any = Body(None), x_user: str | None = Header(None)):
        with database.sessions() as session:
            user = authenticate(session, x_user)
            record = get_issue(session, user, issue_id)
            check_warehouse(session, user, record["warehouseId"])
            if user.role == "REPORTER" or user.role == "ENGINEER" and record["issuedById"] != user.id:
                raise AppError("NO_PERMISSION", "无权退回此领用记录。")
            body = object_body(body)
            integer(body, "issueVersion")
            integer(body, "inventoryVersion")
            if "requestId" in body:
                nonblank(body, "requestId", limit=64)
            if {"quantity", "warehouseId", "itemId"} & set(body):
                raise AppError("VALIDATION_ERROR", "整单退回不能改变数量、仓库或物资。")
        return return_material(database, configuration.exam_now, user, issue_id,
                               body["issueVersion"], body["inventoryVersion"])

    def chat_body(body: Any):
        body = object_body(body)
        nonblank(body, "message")
        if "sessionId" in body:
            nonblank(body, "sessionId", limit=64)
        return body

    @app.post("/api/stock-transfers/preview")
    def transfer_preview(body: Any = Body(None), x_user: str | None = Header(None)):
        with database.sessions() as session:
            user = authenticate(session, x_user)
            require_manager(user)
            body = object_body(body)
            for field in ("itemId", "fromWarehouseId", "toWarehouseId"):
                integer(body, field, minimum=1)
            integer(body, "quantity", quantity=True, minimum=1)
            check_warehouse(session, user, body["fromWarehouseId"])
            check_warehouse(session, user, body["toWarehouseId"])
            pending("T3 调拨预览")

    @app.post("/api/stock-transfers/confirm")
    def transfer_confirm(body: Any = Body(None), x_user: str | None = Header(None)):
        with database.sessions() as session:
            require_manager(authenticate(session, x_user))
            body = object_body(body)
            nonblank(body, "confirmToken")
            pending("T3 调拨确认")

    @app.post("/api/agent/run", responses={200: {
        "description": "考生实现：页面以 Accept: text/event-stream 接收 meta/progress/result 或 error；JSON 为可选兼容。协议见 contracts/specs/t3.md。",
        "content": {
            "text/event-stream": {"schema": {"type": "string"}},
            "application/json": {"schema": {"type": "object"}},
        },
    }})
    def agent(body: Any = Body(None), x_user: str | None = Header(None), accept: str | None = Header(None)):
        with database.sessions() as session:
            authenticate(session, x_user)
            body = chat_body(body)
            if "confirmToken" in body:
                nonblank(body, "confirmToken")
            raise AppError("SKILL_NOT_IMPLEMENTED", "T3 SSE连续对话、自然语言路由与编排待考生实现。")

    @app.post("/api/dev/reset")
    def reset(body: Any = Body(None)):
        dev_allowed()
        if body is None:
            dataset = default_dataset()
        else:
            body = object_body(body)
            if set(body) != {"dataset"}:
                raise AppError("VALIDATION_ERROR", "重置请求须为 {dataset: ...} 或无请求体。")
            dataset = body["dataset"]
        return reset_dataset(database, dataset)

    @app.get("/api/dev/clock")
    def clock_get():
        dev_allowed()
        with database.sessions() as session:
            return {"now": iso(now(session, configuration.exam_now))}

    @app.post("/api/dev/clock")
    def clock_set(body: Any = Body(None)):
        dev_allowed()
        body = object_body(body)
        requested = utc(nonblank(body, "now"))
        with database.sessions() as session:
            timestamps = []
            for record in read_history(session):
                timestamps += [utc(record[key]) for key in ("issuedAt", "returnedAt") if record[key]]
            metadata = MetaData()
            metadata.reflect(bind=session.connection())
            for table in metadata.tables.values():
                for name in ("occurred_at", "created_at", "updated_at", "issued_at", "returned_at"):
                    if name in table.c:
                        for value in session.execute(select(table.c[name])).scalars():
                            if value is not None:
                                timestamps.append(stored_utc(value))
            if timestamps and requested < max(timestamps):
                raise AppError("VALIDATION_ERROR", "时钟不能早于已有业务记录。")
            clock = session.get(ExamClock, 1)
            if clock:
                clock.now = requested
            else:
                session.add(ExamClock(id=1, now=requested))
            session.commit()
        return {"now": iso(requested)}

    return app


app = create_app()

