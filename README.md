# AI Material Exam

MaterialOps 设备运维备件业务助手的预置工程，围绕备件领用与整单退回、保障建议与人工决定、备件调拨对话助手开展开发实战。

预置工程包含业务需求、任务文件、运行代码、数据结构、接口规范、参考页面、基础测试和演示数据。业务需求见 [tasks/REQUIREMENTS.md](tasks/REQUIREMENTS.md)，开发任务见 [tasks/TASK.md](tasks/TASK.md)。

## 开始使用

先阅读工程内已提供的 [业务需求](tasks/REQUIREMENTS.md) 和 [开发任务](tasks/TASK.md)，然后在仓库根目录运行：

**Windows PowerShell：**

```powershell
./exam.ps1 preflight
./exam.ps1 start
```

**Bash（Linux、macOS 或 Git Bash）：**

```bash
bash exam preflight
bash exam start
```

工程使用 Python 3.11 及以上、`uv`、Node.js 22.18 及以上、npm 和 SQLite；前端为 React/Vite/TypeScript，后端为 FastAPI/SQLAlchemy，数据库迁移使用 Alembic。

`preflight` 检查启动工具是否可用。首次启动会安装锁定依赖、执行迁移并加载演示数据；安装依赖需要访问对应软件源。`start` 在当前终端持续运行，按 `Ctrl+C` 停止前后端服务。重复启动保留已有业务数据。

默认地址：

- Web：[http://127.0.0.1:5173](http://127.0.0.1:5173)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

在另一个终端进入仓库根目录，运行 `./exam.ps1 test` 或 `bash exam test`，检查后端基础测试、素材校验测试、前端测试及构建。测试通过不代表 T1、T2、T3 已完成，具体实现要求见 [开发任务](tasks/TASK.md) 和 [开发契约](contracts/common.md)。

需要恢复演示数据时运行 `./exam.ps1 reset` 或 `bash exam reset`。**该命令会清空所选数据库中的业务数据和操作记录，再加载演示数据。** 三个阶段沿用同一应用和数据库，不使用 `reset` 切换阶段。

更多命令和自定义端口用法见 [scripts/README.md](scripts/README.md)。`starter` 仅供组织方检查预置边界，业务完成后不要求通过；`verify-data` 只校验素材，不能代替业务验收。

## 模型配置

将 [app/backend/.env.example](app/backend/.env.example) 复制为 `app/backend/.env`，填写组织方提供的配置：

```dotenv
BASE_URL=https://your-model-service.example/v1
MODEL=your-model-name
API_KEY=your-api-key
```

客户端使用兼容 `chat/completions` 的模型接口。示例仅为占位值；普通保障建议及维护回答应实际调用模型。模型配置也可通过进程环境变量提供，配置后重启后端生效。不要提交 `.env` 或真实密钥。

知识资料已预置为只读文件，无需导入或配置 embedding 服务。

## 目录

| 目录 | 内容 |
| --- | --- |
| `app/` | 前后端代码、预置模型与迁移、参考页面及基础测试 |
| `contracts/` | 通用规则、阶段接口约定、JSON Schema 和验收场景说明 |
| `resources/` | 演示业务数据、只读知识、业务配置及数据 Schema |
| `tasks/` | 已预置的业务需求（`REQUIREMENTS.md`）和开发任务（`TASK.md`） |
| `scripts/` | 启动、重置、测试和素材校验脚本 |
| `runtime/` | 本地数据库、日志和缓存，运行时生成，不提交 Git |

默认数据库为 `runtime/data/materialops.db`，首次加载 [material-kit-dataset.json](resources/demo/material-kit-dataset.json)。维护资料见 [knowledge-baseline.json](resources/demo/knowledge-baseline.json)，素材说明见 [resources/README.md](resources/README.md)。

PowerShell 启动日志保存在 `runtime/logs/`，依赖及测试缓存位于 `runtime/cache/`。停止服务后可清理日志和缓存，保留 `runtime/data/` 中的业务数据。缺少数据库时，下次启动会重新创建并加载演示数据。

需要使用独立数据库时，在启动前设置进程环境变量 `DATABASE_URL`。直接启动后端、CLI 或 Alembic 时，默认也使用上述共享数据库。运行说明见 [app/README.md](app/README.md)。

## 开发约定

- 复用现有技术栈、预置数据结构和页面；新增数据库结构应追加 Alembic 迁移，不覆盖已有业务数据。
- T1 复用单物资及套料父子结构，完成原子领退；T2 将最终补充计划和决定保存在分析记录；T3 通过 SSE 对话展示进度，经本人确认后办理调拨。详细要求见 [T1](contracts/specs/t1.md)、[T2](contracts/specs/t2.md)、[T3](contracts/specs/t3.md)。
- 服务端执行当前身份和权限检查，输入、资料及模型输出不能改变授权。
- 数据库存储 UTC，页面按 `Asia/Shanghai` 显示；原始领用统计按北京时间计算，分物资和单位展示。
- 业务变更在事务内完成，失败不留部分变更，并返回结构化错误；结果未知时先核对，不自动重发写请求。
- 不提交运行数据库、日志、缓存、依赖目录或真实密钥；保留源代码、依赖锁文件、迁移和有效测试。
