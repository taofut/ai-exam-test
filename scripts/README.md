# 工程脚本使用说明

统一通过工程根目录的 `exam.ps1`（PowerShell）或 `exam`（Bash）运行脚本。以下命令和路径均以工程根目录 `exam-1104/` 为基准。

## 命令速查

调用格式：PowerShell 使用 `./exam.ps1 <命令>`，Bash 使用 `bash exam <命令>`。

| 命令 | 作用 | 使用说明 |
| --- | --- | --- |
| `preflight` | 检查 `uv`、Node.js 和 npm 是否可用 | 启动前检查工具环境 |
| `start` | 准备锁定依赖、初始化数据并启动前后端 | 重复启动保留已有业务数据 |
| `reset` | 清空所选数据库并重新加载演示数据 | 仅在需要恢复演示数据时使用 |
| `test` | 运行后端基础测试、素材校验测试、前端测试及构建 | 验证基础工程，不代表业务功能已完成 |
| `starter` | 检查发题前的占位边界及预置历史回填 | 供组织方检查；业务完成后无需通过 |
| `verify-data` | 只读校验两份业务数据及预置知识 | 校验素材，不代替业务验收 |

> **重置会清空数据：** `reset` 作用于当前选定的数据库。三个阶段必须继续使用同一数据库，不使用 `reset` 切换阶段。

## 启动与端口配置

### Windows PowerShell

```powershell
./exam.ps1 preflight
./exam.ps1 start -BackendPort 8000 -FrontendPort 5173
```

`-BackendPort` 和 `-FrontendPort` 均可省略，默认值分别为 `8000` 和 `5173`。

### Bash

```bash
bash exam preflight
bash exam start
```

通过环境变量指定端口：

```bash
MATERIAL_API_PORT=8000 MATERIAL_WEB_PORT=5173 bash exam start
```

| 服务 | 默认端口 | 默认访问地址 |
| --- | --- | --- |
| 后端 API | `8000` | [API 文档](http://127.0.0.1:8000/docs) |
| 前端 Web | `5173` | [应用页面](http://127.0.0.1:5173) |

`start` 在当前终端持续运行，按 `Ctrl+C` 停止前后端服务。运行测试或校验命令时，请在另一个终端进入工程根目录执行。

## 数据库、日志与缓存

| 路径 | 内容 | 管理说明 |
| --- | --- | --- |
| `runtime/data/materialops.db` | 默认 SQLite 数据库 | 保存各阶段业务数据 |
| `runtime/logs/` | PowerShell 启动产生的服务日志 | 排查启动或运行异常时查看 |
| `runtime/cache/` | 依赖和测试缓存 | 与业务数据库分开存放 |

直接使用后端 CLI、uvicorn 或 Alembic 时，默认连接同一数据库。需要切换到独立测试库时，设置进程环境变量 `DATABASE_URL`。

停止服务后可清理日志和缓存；清理 `runtime/logs/`、`runtime/cache/` 不会删除默认业务数据库。上述运行产物不纳入提交。

## 素材校验

**PowerShell：**

```powershell
./exam.ps1 verify-data
```

**Bash：**

```bash
bash exam verify-data
```

校验使用以下预置文件：

| 文件 | 内容 |
| --- | --- |
| [material-kit-dataset.json](../resources/demo/material-kit-dataset.json) | 默认业务数据 |
| [seed-data.json](../resources/demo/seed-data.json) | 示例业务数据 |
| [knowledge-baseline.json](../resources/demo/knowledge-baseline.json) | 应用直接使用的只读知识 |

知识校验包括 Schema 结构、文档 ID 唯一性，以及与默认业务数据的部门、物资关联。

校验程序本身不连接网络，不连接、重置或写入数据库。命令执行前会准备后端依赖，首次安装依赖可能需要访问软件源。

## 测试范围与临时目录

`test` 验证基础工程；`starter` 除占位检查外，还会在隔离数据库中构造考生表，验证预置历史回填。**考生完成业务后无需通过 `starter` 测试组。**

测试临时库统一放在 `runtime/cache/pytest-tmp/` 下，避免依赖系统共享临时目录权限：

| 子目录 | 对应测试 |
| --- | --- |
| `backend/` | `test` 中的后端基础测试 |
| `resources/` | `test` 中的素材校验测试 |
| `starter/` | `starter` 占位与历史回填检查 |

> **临时目录会被重建：** 每次 pytest 运行都会重建对应临时目录，请勿存放手工数据，也不要在同一工程副本中并发运行同一组测试。
