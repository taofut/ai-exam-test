# 接口与功能规范

本目录定义 MaterialOps 的通用规则、功能规范、接口字段和测试约定。业务范围见工程内已预置的 [业务需求](../tasks/REQUIREMENTS.md) 和 [任务说明](../tasks/TASK.md)。

```text
contracts/
├── README.md    阅读入口
├── common.md    通用规则
├── errors.json  错误码和 HTTP 状态
├── specs/       T1、T2、T3 功能规范
├── schemas/     接口字段的 JSON Schema
└── testing/     开发接口和测试约定
```

## 阅读顺序

先阅读上述业务需求和任务说明，再查阅本目录：

1. 阅读[通用规则](common.md)。
2. 阅读要实现的 T1、T2 或 T3 功能规范。
3. 查阅对应的 JSON Schema，确定字段格式。
4. 本地开发和测试时，阅读[开发接口和页面标识](testing/dev-interfaces.md)。

## 规范职责与冲突处理

发生同一事项表述不一致时，按以下顺序处理；同层文件应互相补充，明确细则不能扩大已规定的考核范围。

| 顺序 | 文档 | 职责 |
| --- | --- | --- |
| 1 | `tasks/REQUIREMENTS.md`、`tasks/TASK.md` | 业务目标、功能范围、阶段时长和明确不考的内容 |
| 2 | `contracts/common.md`、`contracts/specs/t1.md`～`t3.md` | 权限、事务、统计、知识和确认规则；阶段规范在共同约束内细化对应业务 |
| 3 | `contracts/schemas/`、`contracts/errors.json`、`resources/schemas/` | 请求响应、资源字段结构及错误码；Schema 通过不代表业务校验通过 |
| 4 | `contracts/testing/`、`resources/config/`、示例、README 和代码注释 | 代表验收场景、配置及使用说明，不另增必考功能 |


## 通用规则与功能规范

| 文件 | 规范 |
| --- | --- |
| [通用规则](common.md) | 身份、权限、事务、失败处理和时间 |
| [T1：单物资与维修套料领退](specs/t1.md) | 同仓套料、单物资领用、原单全退、版本保护及本日统计 |
| [T2：备件保障研判](specs/t2.md) | 只读知识、模型建议、引用、人工复核和三种决定 |
| [T3：备件调拨对话助手](specs/t3.md) | 对话查询、研判复用、SSE 进度、预览确认和原子调拨 |
| [错误码](errors.json) | 错误码和 HTTP 状态 |

## 接口字段

| 文件 | 用途 |
| --- | --- |
| [ai-replenishment.schema.json](schemas/ai-replenishment.schema.json) | 建议对象：仓库、物资、补充数量、理由和知识引用等 |
| [advice-response.schema.json](schemas/advice-response.schema.json) | 分析完整响应：建议、库存版本、复核标记、本日统计、知识依据及最终决定 |
| [advice-edit.schema.json](schemas/advice-edit.schema.json) | 修改后采纳请求：最终数量、理由和复核确认 |
| [agent-response.schema.json](schemas/agent-response.schema.json) | 助手完整结果：回答、会话、调拨预览、确认令牌和执行结果 |
| [agent-stream-event.schema.json](schemas/agent-stream-event.schema.json) | SSE 事件：`meta`、`progress`、`result` 和 `error` |

分析响应中的 `suggestion` 表示原建议，字段约定见 `ai-replenishment.schema.json`；`context` 保存实际库存、本日统计和本次知识依据，`knowledgeReferences` 为支持结论的知识引用。历史单据 `references` 仅兼容空数组，可省略。

`finalSuggestion` 表示人工决定后的最终补充计划，对应分析记录内的 `final_suggestion`；不另建计划草稿单，采纳不改变库存。直接采纳和拒绝的请求字段见 [T2 规范](specs/t2.md)。

SSE 的 `result` 使用 `agent-response.schema.json` 定义完整业务结果。`progress` 只表示处理进度，不代表授权确认或业务成功；`toolTrace` 为可选调试信息。

JSON Schema 约束字段格式，不能替代服务端的权限、来源真实性、库存版本及事务校验。T1 领退和套料的请求、响应见 [T1 规范](specs/t1.md)。

## 开发和测试

| 文件 | 用途 |
| --- | --- |
| [开发接口和页面标识](testing/dev-interfaces.md) | 健康检查、开发身份、数据重置、模拟时间、页面标识及考前验证 |
| [test-faults.json](testing/test-faults.json) | 模型故障测试值、本地夹具及受控 HTTP 测试约定 |
| [runtime-fixtures.json](testing/runtime-fixtures.json) | 各功能的正常及代表性异常场景说明，不是可执行测试服务 |

重置数据的格式见 [dataset.schema.json](../resources/schemas/dataset.schema.json)，默认演示数据见 [material-kit-dataset.json](../resources/demo/material-kit-dataset.json)。

只读知识见 [knowledge-baseline.json](../resources/demo/knowledge-baseline.json)，结构见 [knowledge-baseline.schema.json](../resources/schemas/knowledge-baseline.schema.json)。业务配置见 [material-policy.json](../resources/config/material-policy.json)。示例提供可运行素材，不规定固定实体 ID、名称或业务数值。

## 固定用词

| 用词 | 含义 |
| --- | --- |
| 模拟时间 | 服务端记录业务时间和计算本日领用量使用的时钟，HTTP 超时仍使用真实经过时间 |
| 当前库存 | 指定仓库、物资的可用账面数量，以本次业务查询为准 |
| 维修套料 | 同一仓库 2～5 种不同物资组成的一张领用父单及其明细 |
| 原单整单退回 | 全部未使用、完好的备件按原单数量一次退回原仓；套料子明细不能单退 |
| 本日原始领用量 | 北京时间本日的领用数量，按物资和单位统计；退回不抵扣，套料父单不重复累计 |
| 待办补充计划 | 采纳后保存在分析记录内的最终数量、理由和决定，不代表采购、到货或调拨授权 |
| 调拨预览 | 展示两库、物资、数量及前后余额的待确认内容，预览不占库存 |
| 明确确认 | 本人确认当前有效预览；资料、模型输出或 T2 采纳不能代替确认 |
| 结果待核对 | 未取得确定的执行结果，不能认定成功或已回滚；T1 查询已有记录，T3 在原有效会话内显式“核对/完成原次确认”，不自动重发写请求 |
