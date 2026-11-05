# Agent.md — MaterialOps T1/T2 交付说明

本文件是评审入口：启动、健康检查、停止、数据重置、测试入口、账号与已知限制均以本文件为准，命令均在仓库根目录（`exam-1104/`）逐字执行。已交付范围：T1「单物资与维修套料领退」（不调用模型）、T2「备件保障研判」（调用模型并落人工决策）。

## 1. 结构说明

```text
exam-1104/
├── exam                      # Bash 统一入口（bash exam preflight|start|reset|test）
├── exam.ps1                  # PowerShell 统一入口（./exam.ps1 preflight|start|reset|test）
├── scripts/exam.sh           # 启动、重置、测试的实际实现（依赖准备、端口、数据库路径）
├── Agent.md                  # 本文件
├── docs/设计说明.md          # 独立设计文档（T1+T2：需求、方案、模型、契约、权限、AI 策略）
├── app/backend/              # FastAPI + SQLAlchemy 2.0 + Alembic + SQLite
│   ├── src/materialops/
│   │   ├── main.py           # 应用装配、/health、单物资领用与整单退回路由
│   │   ├── models.py         # ORM 模型（t_inventory、t_material_issue、t_material_issue_order、t_stock_movement、t_audit_log、t_ai_call_log 等）
│   │   ├── api/issue_orders.py   # T1 套料四个路由：列表、领用、详情、整单退回
│   │   ├── api/advice.py         # T2 三个路由：发起分析、三种决定、按 callId 重读
│   │   ├── services/ledger.py    # T1 公共助手：单号、流水、审计、权限矩阵、公开序列化
│   │   ├── services/issue.py     # T1 单物资领用、原单整单退回（各一个事务）
│   │   ├── services/kit.py       # T1 同仓套料领用、整单退回、列表、详情
│   │   ├── services/queries.py   # 库存、领用历史、本日统计查询
│   │   ├── services/knowledge.py # T2 只读知识：可见性、适用性、引用校验、复核项
│   │   ├── services/advice.py    # T2 分析、模型调用与降级、三种决定、按 callId 重读
│   │   ├── ai/client.py          # 模型客户端（超时/网关/非法 JSON 夹具入口）
│   │   ├── ai/prompts.py         # 提示词渲染（replenishment-v1）
│   │   └── alembic/versions/     # 预置迁移 0001～0006（T1/T2 均未新增迁移）
│   └── tests/                # 后端测试，含 test_timed_kit_issue.py、test_timed_advice.py
├── app/frontend/             # React 19 + TypeScript + Vite（无路由库）
│   ├── src/components/InventoryDetail.tsx  # 库存详情 + 套料清单弹层 + 保障建议面板挂载
│   ├── src/components/AiPanel.tsx          # T2 保障建议面板（分析、引用原文、复核、三种决定）
│   ├── src/components/IssueList.tsx        # 本人记录：套料父单分组、单物资记录
│   ├── src/kitOrder.ts                     # 套料领用/退回请求封装
│   ├── src/returnIssue.ts                  # 单物资整单退回封装
│   └── tests/                # 前端单元测试（vitest）
├── contracts/                # 公共契约、T1 契约、错误码、页面锚点
├── resources/                # 演示数据与只读知识（material-kit-dataset.json 等）
├── tasks/                    # 业务需求与开发任务
└── runtime/                  # 数据库、日志、缓存，运行时生成，不提交 Git
```

默认数据库为 `runtime/data/materialops.db`，首次启动自动建库、迁移并加载 `resources/demo/material-kit-dataset.json`。

### T1 业务接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/inventories/{inventoryId}/issue` | 单物资领用，扣减库存并生成真实单据 |
| `POST` | `/api/material-issues/{issueId}/return` | 单物资原单整单退回，原量原仓入库 |
| `GET` | `/api/material-issue-orders` | 套料父单列表（`mine`、`warehouseId`、`status` 可选） |
| `POST` | `/api/material-issue-orders` | 同仓 2～5 行套料领用，整单原子生效 |
| `GET` | `/api/material-issue-orders/{orderId}` | 套料父单与全部明细 |
| `POST` | `/api/material-issue-orders/{orderId}/return` | 套料父子整单退回 |
| `GET` | `/api/material-issues` | 领用记录（套料明细带 `issueOrderId`） |
| `GET` | `/api/material-issues/stats` | 本日按物资统计，北京时间日界 |

业务请求需带身份头，例如 `X-User: BD-ENGINEER`。

### T2 保障建议接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/inventories/{inventoryId}/ai-replenishment` | 发起一次保障分析：返回建议、本日统计、送检知识与复核项，并落一条 `PENDING` 记录 |
| `POST` | `/api/inventories/{inventoryId}/ai-replenishment/{callId}/adopt` | 直接采纳，请求体 `{"reviewed": true}` |
| `POST` | `/api/inventories/{inventoryId}/ai-replenishment/{callId}/adopt-edited` | 修改后采纳，请求体 `{"suggestedQuantity", "reason", "reviewed"}` |
| `POST` | `/api/inventories/{inventoryId}/ai-replenishment/{callId}/reject` | 拒绝建议，请求体可为空 |
| `GET` | `/api/inventories/{inventoryId}/ai-replenishment/{callId}` | 按记录读取分析结论、最终计划与决定人/时间 |

行为约定（评审可直接用 `curl` 验证）：

- 仅 ADMIN 与 DISPATCHER 可调用，ENGINEER / REPORTER 返回 `403 NO_PERMISSION`，且权限先于入参校验。
- 模型不可用（超时、网关失败、非法 JSON、结构或引用不符）不返回 5xx，而是 `200` + `degraded=true` + 备用建议，并在 `reviewItems` 写明原因。
- 建议数量按固定口径生成：当前余额低于补货点时补至目标库存（不超过 500），达到或高于补货点时建议 `0`；理由须逐项写明余额、补货点、目标库存、本日原始领用量。
- 模型可返回 `needHuman=true`（自称建议人工判断），页面以「模型建议人工判断」提示，但不因此强制复核——强制复核只认契约 F05 的三种情形（缺适用资料、明确冲突、降级）。
- `requiresHumanReview=true` 时采纳必须带 `reviewed=true`，否则 `409 HUMAN_REVIEW_REQUIRED`；采纳前库存版本已变化返回 `409 VERSION_CONFLICT`，拒绝不校验版本。
- 同一条记录只能决定一次，重复决定返回 `409 AI_DECISION_CONFLICT`。

模型故障夹具（仅用于复现失败路径，正常调用不需要该头）：

```bash
curl -s --noproxy '*' -X POST http://127.0.0.1:8000/api/inventories/8101/ai-replenishment \
  -H 'X-User: BD-DISPATCH' -H 'X-Model-Fault: timeout'
```

可取值为 `timeout`、`network`、`invalid_json`、`fake_reference`、`injected`、`low_confidence`。

页面锚点（`data-test`，供自动化操作）：`ai-analyze`、`ai-suggestion`、`ai-issue-stats`、`ai-need-human`、`ai-knowledge-source`、`ai-reviewed`、`ai-adopt`、`ai-edit-adopt`、`ai-reject`、`ai-reviewed-edit`（修改弹窗内的复核勾选）。

## 2. 启动

前置：Python 3.11+、`uv`、Node.js 22.18+、npm、SQLite（首次启动需可访问软件源安装依赖）。

Bash（Linux / macOS / Git Bash）：

```bash
bash exam preflight
bash exam start
```

PowerShell（Windows）：

```powershell
./exam.ps1 preflight
./exam.ps1 start
```

`start` 会在当前终端持续运行，自动准备锁定依赖、执行迁移、加载演示数据，并同时启动前后端：

- Web 页面：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs
- 身份列表：http://127.0.0.1:8000/api/session/users

自定义端口（Bash）：

```bash
MATERIAL_API_PORT=8000 MATERIAL_WEB_PORT=5173 bash exam start
```

重复启动保留已有业务数据；只有 `reset` 会清空业务数据。

## 3. 健康检查

后端就绪后执行（`--noproxy` 让本机回环地址不走系统代理，避免代理返回 502）：

```bash
curl -s --noproxy '*' http://127.0.0.1:8000/health
```

预期响应：

```json
{"status":"ok"}
```

前端页面可访问性检查：

```bash
curl -s --noproxy '*' -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/
```

预期输出 `200`。

## 4. 停止

`start` 在前台运行，在运行它的终端按 `Ctrl+C` 即可同时停止前后端。

若需确认端口已释放（无输出表示已停止）：

```bash
lsof -iTCP:8000 -sTCP:LISTEN
lsof -iTCP:5173 -sTCP:LISTEN
```

若终端已关闭但进程仍在，按端口结束（BSD/macOS 与 Linux 均可执行）：

```bash
lsof -tiTCP:8000 -sTCP:LISTEN | while read -r pid; do kill "$pid"; done
lsof -tiTCP:5173 -sTCP:LISTEN | while read -r pid; do kill "$pid"; done
```

## 5. 数据重置

命令行重置（清空业务数据与操作记录，再加载演示数据）：

```bash
bash exam reset
```

PowerShell：

```powershell
./exam.ps1 reset
```

接口重置（服务运行中，`ALLOW_EXAM_RESET` 默认开启）：

```bash
curl -s -X POST http://127.0.0.1:8000/api/dev/reset
```

命令幂等：连续执行两次，输出与数据状态一致（均回到 `resources/demo/material-kit-dataset.json` 的初始快照）。重置不会切换阶段，T1 完成后继续使用同一数据库。

## 6. 测试入口

全量测试（后端 + 素材校验 + 前端单元测试 + 前端构建）：

```bash
bash exam test
```

PowerShell：

```powershell
./exam.ps1 test
```

单独运行 T1 新增用例（3 条：套料领用业务断言、行集非法拒绝、整单退回）：

```bash
cd app/backend && uv run pytest tests/test_timed_kit_issue.py
```

单独运行 T2 新增用例（2 条：正常分析的字段与统计口径断言、降级与越权边界）：

```bash
cd app/backend && uv run pytest tests/test_timed_advice.py
```

后端全量：

```bash
cd app/backend && uv run pytest
```

前端单元测试与构建：

```bash
cd app/frontend && npm test
cd app/frontend && npm run build
```

当前基线：后端 204 passed / 24 deselected / 2 xpassed（2 个 xpassed 是 T1 修复的两个预置缺陷用例），素材校验 7 passed，前端 9 passed 且构建通过。`24 deselected` 是 `-m "not starter"` 排除的脚手架用例，其中 3 条断言 T2 三个入口返回 `501`，在实现后必然失败，故保持排除；这 3 条不属于任何评分项。

若在受限沙箱中单独跑上面两条单文件命令时出现大量 `FileExistsError: EEXIST ... pytest-of-*`，是该环境对 `mkdir` 的拦截所致，与用例无关；`bash exam test` 已内置独立基目录，不受影响。手工重跑加一个基目录即可：

```bash
cd app/backend && uv run pytest tests/test_timed_advice.py --basetemp=/tmp/pytest-advice
```

## 7. 账号

页面左上角「身份」下拉切换，取值即员工号；接口通过请求头 `X-User: <员工号>` 提供身份。服务端按员工号查询用户与权限，不信任请求体中的角色。

T2 保障建议只对上表中的 `ADMIN`、`DISPATCHER` 开放（`BD-ADMIN`、`BD-DISPATCH`、`BD-SITE-D`、`BD-OTHER-D`）；`ENGINEER`、`REPORTER` 调用返回 `403`，页面也不会渲染保障建议面板。

| 员工号 | 姓名 | 角色 | 部门 | 用途 |
| --- | --- | --- | --- | --- |
| `BD-ADMIN` | 管理员 | ADMIN | 110 设备运维部 | 全仓可见，可代退 |
| `BD-DISPATCH` | 协调员 | DISPATCHER | 110 设备运维部 | 领用、代退 |
| `BD-ENGINEER` | 现场工程师 | ENGINEER | 110 设备运维部 | 领用、退本人单据（默认身份） |
| `BD-PEER` | 同组工程师 | ENGINEER | 110 设备运维部 | 越权校验用（他人单据） |
| `BD-REPORTER` | 申请查看人 | REPORTER | 110 设备运维部 | 只读，领用/退回返回 403 |
| `BD-SITE-D` | 现场协调员 | DISPATCHER | 111 现场保障部 | 跨部门校验 |
| `BD-SITE-E` | 现场工程师 | ENGINEER | 111 现场保障部 | 跨部门校验 |
| `BD-NIGHT-E` | 夜班工程师 | ENGINEER | 112 夜班保障组 | 夜班仓库校验 |
| `BD-ROOM-E` | 机房工程师 | ENGINEER | 113 机房运维组 | 机房仓库校验 |
| `BD-OTHER-D` | 外部协调员 | DISPATCHER | 210 外部保障部 | 跨部门代退校验 |
| `BD-OTHER-E` | 外部工程师 | ENGINEER | 210 外部保障部 | 跨部门领用校验 |
| `BD-OTHER-R` | 外部查看人 | REPORTER | 210 外部保障部 | 只读校验 |
| `BD-EMPTY` | 空仓工程师 | ENGINEER | 310 新建项目部 | 空数据边界 |
| `BD-MOVED` | 调岗工程师 | ENGINEER | 110 设备运维部 | 原部门历史单据校验 |

演示数据的初始库存快照（`now = 2026-10-12T02:00:00Z`）：中心备件仓 `4101` 有 8101 电源模块 10 个、8107 线缆 4 条、8110 风扇 4 个；现场备件仓 `4102` 有 8103 电源模块 0 个、8109 线缆 9 条。

## 8. 已知限制

- 已实现 T1（领用与整单退回）与 T2（备件保障研判）。T3 调拨对话仍是预置占位页，未实现。
- 套料限同仓 2～5 行、物资不重复；行数、重复、混仓、退回行集不符返回 `400 KIT_LINES_INVALID`。
- 所有写操作以页面展示的版本做乐观校验，版本过期返回 `409 VERSION_CONFLICT`，需刷新后重试；库存不足返回 `409 STOCK_INSUFFICIENT`。
- 未实现幂等键与成功响应重放。写请求结果未知（断网/超时）时页面提示到「我的领用」核对，不自动重发。T2 的重复决定由记录状态与条件更新挡住（`409 AI_DECISION_CONFLICT`），同样不做响应重放。
- 本日统计仅支持 `period=TODAY&groupBy=ITEM`，其他取值返回 `400 QUERY_ARGUMENT_INVALID`；套料按明细各计一次，退回不抵扣，未来时间不计入。T2 的 `context.issueStats` 固定为「该仓 + 该物资、全部领用人」，与统计接口同口径。
- 记录页为「本人领用」视角。管理员/协调员的代退能力在后端权限矩阵与接口层实现并经测试覆盖，页面不提供他人单据浏览入口。
- 模拟时间接口 `GET/POST /api/dev/clock` 仅在 `ALLOW_EXAM_RESET=true`（默认）时可用；本日统计按 `Asia/Shanghai` 零点划分，数据库存 UTC。
- T2 的模型能力需将 `app/backend/.env.example` 复制为 `app/backend/.env` 并填写 `BASE_URL`、`MODEL`、`API_KEY` 后才可用。已用真实 OpenAI 兼容端点（`deepseek-flash`）跑通：`8101`（余额 10、补货点 5）两次分析均返回 `degraded=false`、建议 0、引用 2 条且 `quote` 均为正文连续原文；`8113`（余额 1、补货点 6、目标 18）返回建议 17，`usage` 为真实 token 数。
- 该模型带推理过程，单次分析实测 9～46 秒（取决于输出长度）。代码默认超时 15 秒会把真实调用打成降级，需在 `.env` 设置 `MODEL_TIMEOUT_SECONDS`（本机取 90）。`.env` 已被 `.gitignore` 忽略，交付副本若含该文件请自行剔除密钥。
- 模型可能自行返回 `needHuman=true`；页面仅作提示，不触发强制复核，强制复核只认「缺适用资料 / 明确冲突 / 降级」三种情形。
- 模型不可用时一律降级为「目标库存 − 当前余额」的备用数量（`confidence=0`、`degraded=true`），不重试、不切换备用模型，也不返回 5xx；只有库存不可取才返回 404/403。
- 知识库为只读文件 `resources/demo/knowledge-baseline.json`，无新建/编辑/列表/检索接口；`status != ACTIVE`、部门不在权限内、`itemNos` 不含当前物资的资料不进入模型。通用资料只作背景，不能替代物资维护依据——缺维护依据时强制人工复核。
- 资源冲突只认「同一物资多篇有效资料正文中的周期表述互斥」（如「每月」对「每季度」），不做语义推理，也不因「多篇资料」一律触发复核。
- 不实现向量检索、索引热更新、topK 打分、`references`（历史单据引用）、草稿表与审批流；T2 待办计划保存在已有 `t_ai_call_log.final_suggestion` 与 `decision` 内，未新增表与迁移。
- 运行时为单机 SQLite + 单进程 Uvicorn，未做多实例部署与外部数据库适配。

## 9. 交付说明：对预置文件的改动

| 文件 | 改动 | 性质 |
| --- | --- | --- |
| `scripts/exam.sh` | 第 71 行 `wait -n` 改为 `kill -0` 轮询等待 | **启动缺陷修复**。macOS 自带 bash 3.2 不支持 `wait -n`，未修复时 `bash exam start` 打印地址后立即退出（`wait: -n: invalid option`），S0-3 必挂，会连带 B、C 归零 |
| `app/backend/src/materialops/main.py` | 两处 `pending("T1 …")` 占位替换为真实服务调用；T2 三个 `pending` 占位删除并挂载 `advice_router` | 预置接口插槽，T1/T2 要求实现 |
| `app/backend/src/materialops/api/issue_orders.py` | 四个套料路由落地（列表、领用、详情、整单退回） | 预置接口插槽 |
| `app/backend/src/materialops/services/queries.py` | 修正两处预置缺陷：ENGINEER 仓库筛选不得扩大授权范围；本日统计改为北京时间零点日界；并统一统计口径 | T1 契约明文要求修复 |
| `app/backend/src/materialops/services/knowledge.py` | 新增：知识可见性/适用性过滤、复核项、引用三要素校验 | T2 新增文件 |
| `app/backend/src/materialops/services/advice.py` | 新增：分析、模型调用与降级、三种决定、按 callId 重读 | T2 新增文件 |
| `app/backend/src/materialops/api/advice.py` | 新增：三个路由 + 入参白名单 + `reviewed` 布尔校验 | T2 新增文件 |
| `app/backend/tests/test_timed_advice.py` | 新增 2 条测试（业务字段断言、降级与越权边界） | S5 测试资产 |
| `app/frontend/src/components/AiPanel.tsx` | 由未挂载的参考组件接入页面，补本日统计依据、知识原文展开、修改弹窗内复核勾选 | T2 页面 |
| `app/frontend/src/components/InventoryDetail.tsx` | 挂载 `AiPanel`（`permissions.canAnalyze` 为真时） | T2 页面接入 |
| `app/frontend/src/types.ts` | `Analysis.context` 由 `Record<string, unknown>` 收紧为 `AnalysisContext` | 类型收紧，不改运行时 |
| `.gitignore` | 追加 `.workbuddy/` | 让本地工具目录不进入仓库副本，不影响构建 |

未新增数据库迁移：T1 复用预置 `0004_timed_issue_table`、`0005_timed_kit_structure` 的结构，T2 复用 baseline 建立的 `t_ai_call_log`（14 列已含 `context`、`original_suggestion`、`final_suggestion`、`decision`、`inventory_version`），`alembic head` 仍为 `0006_retire_empty_drafts`，`demo-manifest` 与文档中的版本号无需同步。前端未引入路由库与表单校验库，样式只在 `app/frontend/src/styles.css` 末尾追加套料弹层与分组所需规则。

