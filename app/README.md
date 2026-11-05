# 应用工程说明

本目录包含 MaterialOps 起始工程的前后端代码。

## 技术栈

| 部分 | 技术 | 目录 |
| --- | --- | --- |
| 前端 | React、Vite、TypeScript | `app/frontend/` |
| 后端 | FastAPI、SQLAlchemy、SQLite | `app/backend/` |
| 数据库迁移 | Alembic | `app/backend/alembic/` |
| Python 依赖管理 | uv | `app/backend/pyproject.toml`、`app/backend/uv.lock` |


## 启动应用

在工程根目录打开终端，按所用环境执行以下命令。

**Windows PowerShell：**

```powershell
./exam.ps1 preflight
./exam.ps1 start
```

**Bash：**

```bash
bash exam preflight
bash exam start
```

`preflight` 检查启动工具是否可用；`start` 准备锁定依赖并启动前后端。依赖安装和模型连通性检查应在考前完成。

| 入口 | 默认地址 | 用途 |
| --- | --- | --- |
| Web 页面 | [http://127.0.0.1:5173](http://127.0.0.1:5173) | 访问应用 |
| API 文档 | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | 查看和调试接口 |
| 身份列表 | [http://127.0.0.1:8000/api/session/users](http://127.0.0.1:8000/api/session/users) | 查看可用的 BD 身份 |

启动命令持续占用当前终端，按 `Ctrl+C` 停止服务。自定义端口见 [脚本使用说明](../scripts/README.md)。

## 配置模型

将 [backend/.env.example](backend/.env.example) 复制为 `app/backend/.env`，填写模型配置；也可通过进程环境变量提供，进程环境变量优先于 `.env`。

| 配置项 | 作用 | 填写说明 |
| --- | --- | --- |
| `BASE_URL` | 模型服务的接口基础地址 | 默认 `https://api.openai.com/v1`，按实际服务修改；客户端自动追加 `/chat/completions` |
| `MODEL` | 请求使用的模型名称 | 调用模型时必填，默认为空 |
| `API_KEY` | 模型服务的访问密钥 | 调用模型时必填，默认为空，通过 Bearer 请求头发送 |
| `MODEL_TIMEOUT_SECONDS` | 模型 HTTP 请求超时参数，单位为秒 | 可选，默认 `15`；需要调整时取消示例文件中该行的注释 |

工程已提供模型客户端，可直接复用。修改配置后重启后端生效，真实密钥和 `.env` 文件不应提交。

### 高级配置

以下配置已有代码默认值，日常开发通常无需填写。需要覆盖时，可添加到 `.env` 或设置进程环境变量；通过工程脚本切换数据库时，请遵循下方说明。

| 配置项 | 默认值 | 适用场景 |
| --- | --- | --- |
| `DATABASE_URL` | 指向工程根目录 `runtime/data/materialops.db` 的 SQLite 连接地址 | 使用独立数据库 |
| `CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | 浏览器跨域直连后端时，允许的页面来源发生变化；多个来源用逗号分隔 |

通过 `exam.ps1` 或 `exam` 启动、重置时，脚本会优先使用进程中的 `DATABASE_URL`；未设置时，会将默认库地址写入进程环境变量。因此，**通过工程脚本切换数据库，应在运行前设置进程环境变量 `DATABASE_URL`，仅修改 `.env` 中的值会被脚本覆盖。**

默认前端通过 Vite 代理访问 `/api`，通常无需调整 `CORS_ORIGINS`。它控制浏览器跨域访问许可，不用于设置服务监听端口。

接口及测试约定见 [开发测试接口](../contracts/testing/dev-interfaces.md)。

## 数据库与运行目录

| 路径 | 用途 |
| --- | --- |
| `runtime/data/materialops.db` | 默认 SQLite 数据库 |
| `runtime/logs/` | PowerShell 启动时生成的服务日志 |
| `runtime/cache/` | 依赖缓存和测试缓存 |

直接使用后端 CLI、uvicorn 或 Alembic 时，默认连接同一数据库。需要使用独立数据库时，在启动前设置进程环境变量 `DATABASE_URL`。

> **阶段衔接：** 三个阶段沿用同一数据库，进入后续阶段时不要执行 `reset`。该命令会清空所选数据库并重新加载演示数据。

`runtime/` 中的数据库、日志和缓存均为本地运行产物，提交时不包含这些内容。

## 验证工程

在另一个终端进入工程根目录，根据需要运行以下命令：

| 命令 | PowerShell | Bash | 验证范围 |
| --- | --- | --- | --- |
| `test` | `./exam.ps1 test` | `bash exam test` | 后端基础测试、素材校验测试、前端测试及构建 |
| `starter` | `./exam.ps1 starter` | `bash exam starter` | 发题前的占位边界与预置历史加载检查 |

**基础测试通过不代表考生业务功能已经完成。** `starter` 供组织方检查起始工程，考生完成业务后无需通过此组；功能验收以正式任务及开发契约为准。
