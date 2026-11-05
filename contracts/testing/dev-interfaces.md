# 开发接口和页面标识

本文件列出 MaterialOps 工程用于启动检查、重置和本地测试的接口及页面标识。业务接口和完成范围见 [公共契约](../common.md) 及 [T1](../specs/t1.md)、[T2](../specs/t2.md)、[T3](../specs/t3.md)。

## 启动检查

```text
GET /health
```

成功响应为 `{ "status": "ok" }`，用于确认后端可访问，不代表业务功能已完成。

从仓库根目录运行 `./exam.ps1 preflight` 或 `bash exam preflight` 检查启动工具，运行 `start` 启动服务。默认 Web 为 `http://127.0.0.1:5173`，API 文档为 `http://127.0.0.1:8000/docs`。完整命令见 [运行说明](../../README.md)。

## 开发身份

```text
GET /api/session/users
GET /api/session/me
```

`users` 返回演示用户列表，包含 `id`、`employeeNo`、`name`、`role`、`deptId` 和 `deptName`。页面通过员工号切换身份，同名用户以员工号和部门区分。

业务请求和 `me` 接口通过请求头提供身份，例如：

```http
X-User: BD-ENGINEER
```

- 服务端按员工号查询当前用户及权限，不信任请求体中的 `userId`、`role`。
- 缺少身份返回 `401 AUTH_REQUIRED`，员工号不存在返回 `401 AUTH_INVALID`。
- 用户列表是开发身份选择入口，不是生产环境的登录或认证方案。

## 重置演示数据

```text
POST /api/dev/reset
```

请求体可以为空，默认加载 [material-kit-dataset.json](../../resources/demo/material-kit-dataset.json)。也可以提交 `{ "dataset": ... }`，其中 `dataset` 为完整数据对象，格式见 [dataset.schema.json](../../resources/schemas/dataset.schema.json)。

- **接口会清空当前数据库中的业务数据和操作记录，再加载指定数据。** 仅用于开发和独立测试，不用于阶段切换。
- 只有 `ALLOW_EXAM_RESET=true` 时可用；关闭时返回 `403 NO_PERMISSION`。模拟时间的读取和设置接口也受此开关控制。
- 写入前校验结构、唯一编号、外键、部门树及时间关系；非法数据返回 `422 VALIDATION_ERROR`，不能先清库再报错。
- `inventories` 是数据集 `now` 时刻的库存快照。导入领用及退回历史不再次扣增库存；普通历史的 `issueOrderId` 为 `null`。
- `issuedAt` 不得晚于 `now`；非空 `returnedAt` 必须位于 `issuedAt` 与 `now` 之间。时间使用带时区的 ISO 8601 格式。
- 重置成功后，旧数据对应的会话和未消费预览失效。预置知识是独立的只读文件，不通过此接口修改或导入。

成功响应包含 `status`、`now` 和各类导入数据的 `counts`。命令行 `./exam.ps1 reset` 或 `bash exam reset` 同样会重置所选数据库；普通 `start` 保留已初始化的数据。

## 读取和设置模拟时间

```text
GET /api/dev/clock
POST /api/dev/clock
```

POST 请求体：

```json
{ "now": "2026-10-12T02:00:00Z" }
```

成功响应为 `{ "now": "2026-10-12T02:00:00Z" }`，GET 返回当前模拟时间。

- 服务端使用模拟时间计算本日领用量及记录业务办理时间，不使用浏览器本地时间。
- 数据库存储 UTC；本日统计按北京时间零点划分，页面按 `Asia/Shanghai` 显示。
- 新时间不得早于已有领用、退回及接口检查的业务记录时间；格式非法、无时区或早于记录时返回 `422 VALIDATION_ERROR`。
- 数据集导入时设置模拟时间；数据库中没有时钟记录时使用配置 `EXAM_NOW`。修改环境变量不会覆盖已保存的时钟记录。
- 模型 HTTP 超时使用真实经过时间，不随业务模拟时钟改变。

## 页面标识

页面使用 `data-test` 定位。保留对应功能的既有名称和实体关联属性；新增标识可自定，不因测试标识另建业务页面。重复出现的行或按钮应通过真实实体 ID 定位，不按固定数组位置选择。

| 功能 | `data-test` | 附加属性或说明 |
| --- | --- | --- |
| 身份切换 | `identity-select` | 选项值为 `employeeNo` |
| 库存列表及行 | `inventory-list`、`inventory-row` | 行带 `data-inventory-id` |
| 单物资领用 | `issue-quantity`、`issue-submit` | 数量输入及提交按钮 |
| 本人记录及全退 | `my-issues`、`issue-return` | 退回按钮带 `data-issue-id` |
| 套料清单 | `kit-open`、`kit-item`、`kit-quantity`、`kit-submit` | 同仓清单的打开、物资、数量及提交 |
| 套料父单及全退 | `kit-parent`、`kit-return` | 带 `data-order-id` |
| 本日统计 | `today-issue-total` | 容器内按物资和单位展示，不混加为一个总数 |
| 保障建议 | `ai-analyze`、`ai-suggestion` | 分析按钮及建议区域 |
| 人工决定 | `ai-reviewed`、`ai-adopt`、`ai-edit-adopt`、`ai-reject` | 复核及三种决定入口 |
| 对话输入及结果 | `agent-input`、`agent-send`、`agent-answer` | 输入、发送及最终回答 |
| 进度与异常 | `agent-progress`、`agent-error` | 当前处理进度、失败或待核对提示 |
| 调拨确认及核对 | `transfer-confirm`、`agent-reconcile` | 本人确认及原操作显式核对 |

标识用于定位和留证，是否完成业务仍以真实接口结果、数据库记录和页面行为判定。

## 模型故障测试

保障分析入口接收 `X-Model-Fault`，取值和夹具要求见 [test-faults.json](test-faults.json)：`timeout`、`network`、`invalid_json`、`fake_reference`、`injected`；`low_confidence` 为可选辅助，不增加限时版考核要求。

- 普通请求使用 `BASE_URL`、`MODEL` 和 `API_KEY` 调用真实模型，配置见 [环境变量示例](../../app/backend/.env.example)。
- `MODEL_FAULT_TRANSPORT=false` 时，客户端使用本地故障夹具；内容故障需要测试代码提供与当前实体和知识依据匹配的 `fault_suggestion`。该参数不是浏览器业务请求字段。
- `MODEL_FAULT_TRANSPORT=true` 时，客户端将故障头转发给组织方受控模型 HTTP 服务，由该服务返回对应响应。现有描述文件不代表受控服务已经部署。
- 故障测试不能绕过授权、实体、引用、复核和事务检查。模型失败可立即降级，不要求自动重试；当前库存取得失败时不得编造备用数量。
- `ALLOW_EXAM_RESET` 仅控制开发数据及时钟接口，不控制模型故障模式。正式模型连通与受控故障验证分别记录结果。

SSE 进度、一次拆帧/粘包、终态及确认结果丢失的验证见 [T3 契约](../specs/t3.md)。延迟、断流、并发和提交前故障由组织方在隔离环境准备，不要求考生搭建评测平台。

