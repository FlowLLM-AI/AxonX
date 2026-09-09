# AxonX

最小异步编排框架：Application 管理 component 生命周期，通过 `run_job()` 执行异步 Job；TaskManager component 管理独立进程中的同步 Task。

```text
Application.run_job(name, **arguments)
  └─ BaseJob → 串行 await BaseStep
       └─ TaskManager.submit(task, config) → run_id
            └─ 独立进程：BaseTask → build_task_steps() → 同步函数
```

## 边界

- `BaseJob` 和 `BaseStep` 可以通过 `get_component(type, name)` 显式访问 component，没有依赖注入或自动依赖排序。
- 每次 Job 调用创建独立 Step 实例和 RuntimeContext。异步方法不能直接运行阻塞 ETL。
- `BaseTask` 原名 BaseFlow，仅持有经 Pydantic 校验的配置、进程内 context 和日志。没有 ApplicationContext，不继承 Component。
- `build_task_steps()` 按需迭代，不提前转成列表；允许 `yield from`、条件分支、循环和 `partial`。Task 内所有同步步骤在同一个进程串行运行，异常立即停止后续步骤。
- Task 的 DataFrame 等大对象留在进程内部。`output_keys` 指定返回字段，输出必须为 JSON 对象，数据集通过文件路径传递。
- `axonx exec` 在当前进程直接执行 Task；远程提交的每次运行获得独立 `run_id`，对应一个新进程。没有 ProcessJob 中间层。

## 目录

```text
axonx/
  application.py              # Application 装配与生命周期
  cli.py                      # 轻量命令行入口
  constants.py                # 跨子系统稳定常量
  components/
    base_component.py
    job/                       # one-shot / interval / cron jobs
    task_manager/
      base_task_manager.py     # Task 管理接口
      local_task_manager.py    # 本机进程实现
      worker.py                # 私有进程入口
    service/                   # 可选 HTTP 服务
    client/                    # HTTP 客户端
  task/
    base_task.py               # BaseTask / BaseConfig / Task 内部同步步骤类型
    common/demo_task.py        # 无可选依赖的内置示例 Task
  steps/                       # 异步 Step 及进程管理适配
  enumeration/
    task_state.py              # TaskState
  schema/
    application_config.py      # 应用配置协议
    plugin.py                  # plugin.yaml 数据协议
    task_run.py                # TaskRun
  config/
    loader.py                 # YAML / JSON 加载、继承与合并
    values.py                 # CLI 值解析与环境变量展开
  plugin/
    artifact.py               # 源码 SHA、wheel 构建与元数据读取
    manifest.py               # Task-only plugin.yaml 解析
    cli.py                    # build / install / deploy
  utils/
    entry_points.py           # Plugin / Config 共享的 entry-point 发现
    dingtalk_utils.py         # 钉钉机器人通知
    tushare_client.py         # Tushare 查询、重试与分页
plugins/polars-demo/            # 可安装的独立 Polars 示例
```

## 启动与提交

Python 3.11+；本机进程管理目前支持 macOS / Linux。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
axonx plugin build plugins/polars-demo
axonx plugin install plugins/polars-demo
axonx start --plugins '["./plugins/polars-demo"]'
```

默认 HTTP 地址 `127.0.0.1:1024`。在另一个终端、同一虚拟环境中运行：

```bash
axonx exec --task sales --output /tmp/sales-local.parquet
axonx submit --task sales --output /tmp/sales.parquet
axonx status
axonx status --run-id 返回的ID
axonx --timeout 3600 wait --run-id 返回的ID
axonx logs --run-id 返回的ID
axonx cancel --run-id 返回的ID
axonx kill --run-id 返回的ID
```

`exec` 自动发现所有已安装插件提供的 Task，并在当前 CLI 进程直接执行。`submit` 使用完全相同的 `--task TASK --field value` 参数形式，返回 ID 后命令即可退出，Task 由常驻服务继续托管。客户端参数放在 command 之前：`axonx --url http://host:port submit --task sales --output /tmp/sales.parquet`。

默认配置提供 submit/status/wait/cancel/kill/logs 等 Task 管理 Job；Worker 通过内部 `report_task_progress` Job 实时上报步骤进度。自定义配置可使用 `extends: default` 继承：

```yaml
extends: default
plugins: [./plugins/polars-demo]
workspace_dir: .axonx
service:
  backend: http
  host: 127.0.0.1
  port: 1024
components:
  task_manager:
    default:
      backend: local
      max_concurrency: 2
      cancel_timeout: 5
      terminate_timeout: 2
jobs:
  sales_and_wait:
    steps:
      - backend: submit_task
        task: sales
      - backend: wait_task
```

`axonx sales_and_wait --output /tmp/sales.parquet` 提交后等待，两个异步 Step 通过 RuntimeContext 传递 run_id。若需按序执行多个 Task，可继续配置 submit/wait 步骤，或者编写异步 Step 根据上一 Task 的输出组装下一次配置。

普通 Job 默认通过 REST 和 MCP 同时公开；设置 `enable_serve: false` 可将其限制为应用内部调用。HTTP 服务提供 `GET /jobs`、`POST /jobs/{name}` 和 Streamable HTTP MCP `/mcp`。`interval` 与 `cron` Job 由 Application 生命周期托管，不会公开；interval 首次立即执行，cron 首次等待表达式指定的时间。

Job 的 `parameters` 使用 JSON Schema，同时作为 `GET /jobs` 的 `inputSchema` 和 MCP Tool 参数定义：

```yaml
jobs:
  submit:
    description: Submit a task for asynchronous execution.
    parameters:
      type: object
      properties:
        task: {type: string}
      required: [task]
      additionalProperties: true
    steps:
      - backend: submit_task
```

```yaml
jobs:
  periodic_status:
    backend: interval
    interval: 300
    steps:
      - backend: task_status
  nightly_status:
    backend: cron
    cron: "0 2 * * *"
    steps:
      - backend: task_status
```

## Python API

```python
from axonx import Application
from axonx.config import resolve_app_config

async def example():
    async with Application(**resolve_app_config(plugins=["./plugins/polars-demo"])) as app:
        response = await app.run_job(
            "submit", task="sales", output="/tmp/sales.parquet"
        )
        record = await app.run_job("wait", run_id=response.answer["run_id"])
        print(record.answer)
```

远程客户端使用统一的 `list_jobs()` / `run_job()` 接口：

```python
from axonx.components.client import HttpClient, McpClient

async with McpClient(url="http://127.0.0.1:1024") as client:
    jobs = await client.list_jobs()
    response = await client.run_job("status")
```

自定义异步 Step 内也可直接使用 Manager：

```python
manager = self.get_component("task_manager", "default")
run_id = await manager.submit("sales", {"output": "/tmp/sales.parquet"})
record = await manager.wait(run_id, timeout=60)
```

所有 Manager 管理方法均为异步。`status()` 返回 TaskRun 列表；`status(id)` / `wait(id)` / `cancel(id)` / `kill(id)` 返回单条快照。`wait()` 超时或调用者取消不会取消 Task。`cancel` 和 `kill` 等待清理完成后返回；`logs` 默认读取最后 64 KiB。

Response.success 表示异步 Job 调用是否成功。查询或等待一个失败 Task 仍是成功的查询，任务结果需检查 `answer.state` 和 `answer.error`。

## 生命周期与状态

状态为 `queued → running → succeeded/failed`；取消经过 `cancelling → cancelled`。

- FIFO 排队，`max_concurrency` 限制同时运行的 Task 数量。
- `cancel` 移除排队任务；运行中先请求协作取消，在 step 之间检查。超过 `cancel_timeout` 发送 SIGTERM，再超过 `terminate_timeout` 强制结束进程组。
- `kill` 立即跳过协作等待并强制结束进程组。自行脱离进程组的子进程不在这个保证内。
- Application 正常关闭时先停止异步调用和后台 Job，再取消、等待和清理 Manager 中的全部任务。HTTP 服务默认最多等待现有请求 1 秒（`service.shutdown_timeout`），随后进入清理，长时间 wait 请求不会阻止退出。
- 记录、进度和日志存放在 `<workspace>/tasks/<manager>/<run_id>/`。重启保留历史记录；未完成记录标记 `lost`，不会按旧 PID 杀进程或自动重跑。
- 当前按一个常驻 Application 独占一个 workspace 使用。服务被 SIGKILL 或机器异常中止不属于正常关闭保证，可能遗留进程；本版没有独立守护执行服务、远程调度或崩溃恢复。

## 插件

插件通过项目路径配置。`PluginComponent` 对源码计算 SHA-256，在内容变化后构建并安装 wheel；wheel 中的 `axonx.plugins` entry point 用于定位只包含 Task 声明的 `plugin.yaml`。

```yaml
tasks:
  sales: axonx_polars_demo.sales:SalesTask
```

插件只能提供 Task，不参与 Component、Step、Job 注册，也不提供应用默认配置。每次执行都会启动新 Worker 并从已安装文件导入 Task，因此更新插件不会影响正在运行的 Task，后续 Task 无需重启 AxonX 即可使用新版本。

远程节点设置 `components.plugin.default.allow_remote_install: true` 后提供 `POST /plugins`；插件列表通过 `list_plugins` Job 查询。可同时配置 `install_token`。本地使用 `axonx plugin deploy ./plugins/polars-demo --url http://IP:PORT --token TOKEN` 构建、校验 SHA-256 并上传 wheel。

Polars 示例 `SalesTask` 用合成数据完成加载、聚合、写 Parquet，总收入为 75；不提供 input 时无需外部数据。

硬件采集和远程机器调度尚未实现，可后续通过独立 component 扩展。

## 验证

```bash
pip install -e '.[dev]' -e plugins/polars-demo
python -m pytest -q
```

覆盖真实进程隔离、惰性步骤、失败记录、FIFO、取消/kill/退出清理、等待超时、插件 Polars 执行和真实 CLI/HTTP 调用。
