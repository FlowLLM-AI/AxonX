# AxonX

最小异步编排框架：Application 管理 component 生命周期，通过 `run_job()` 执行异步 Job；TaskManager component 管理独立进程中的同步 Task。

```text
Application.run_job(name, **arguments)
  └─ BaseJob → 串行 await BaseStep
       └─ TaskManager.submit(task, config) → task_id
            └─ 独立进程：BaseTask → build_task_steps() → 同步函数
```

## 边界

- `BaseJob` 和 `BaseStep` 可以通过 `get_component(type, name)` 显式访问 component，没有依赖注入或自动依赖排序。
- 每次 Job 调用创建独立 Step 实例和 RuntimeContext。异步方法不能直接运行阻塞 ETL。
- `BaseTask` 原名 BaseFlow，持有经 Pydantic 校验的配置、进程内 context、完整 TaskStatus 和日志。没有 ApplicationContext，不继承 Component。
- `build_task_steps()` 按需生成 step，允许根据前序 step 的结果决定后续步骤。Worker 每发现一个 step 都会更新并全量上报当前状态；只有任务结束后才能确定最终 step 总数。Task 内所有同步步骤在同一个进程串行运行，异常立即停止后续步骤。
- Task 的 DataFrame 等大对象留在进程内部。`output_keys` 指定返回字段，输出必须为 JSON 对象，数据集通过文件路径传递。
- `axonx exec` 在当前进程直接执行 Task；远程提交的每次运行获得独立 `task_id`，对应一个新进程。没有 ProcessJob 中间层。

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
    service/                   # 可选 HTTP 服务
    client/                    # HTTP 客户端
  task/
    base_task.py               # BaseTask / BaseConfig / Task 内部同步步骤类型
    task_runner.py             # 主线程同步执行和 step 生命周期
    task_status_manager.py     # 与传输无关的 TaskStatus 状态机
    status_sink.py             # Worker 后台状态发送
    worker.py                  # 私有隔离进程入口
    common/demo_task.py        # 无可选依赖的内置示例 Task
  steps/                       # 异步 Step 及进程管理适配
  enumeration/
    task_state.py              # TaskState
  schema/
    application_config.py      # 应用配置协议
    plugin.py                  # plugin.yaml 数据协议
    task_status.py             # TaskStatus / TaskStep
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
axonx list
axonx status --task-id 返回的ID
axonx --timeout 3600 wait --task-id 返回的ID
axonx logs --task-id 返回的ID
axonx cancel --task-id 返回的ID
```

`exec` 自动发现所有已安装插件提供的 Task，并在当前 CLI 进程直接执行。`submit` 使用完全相同的 `--task TASK --field value` 参数形式，返回 ID 后命令即可退出，Task 由常驻服务继续托管。客户端参数放在 command 之前：`axonx --host-ip 127.0.0.1 --host-port 1024 submit --task sales --output /tmp/sales.parquet`。

默认配置提供 submit/list/status/wait/cancel/logs 等 Task 管理 Job。`exec` 在当前进程同步执行；`submit` 启动的 Worker 也始终在主线程同步执行 Task step。纯状态机 `TaskStatusManager` 生成完整快照，独立后台线程通过父子进程本地 socket 上报，不阻塞计算步骤。自定义配置可使用 `extends: default` 继承：

每个 Task 必须声明 `task_type`。Task ID 格式为 `{task_type}#{UTC时间}#{suffix}`；框架自动记录每个 step 的开始和完成时间，step 内可调用 `self.report_progress(percentage)` 手动更新百分比。Task step 必须是同步 callable，不能声明为 `async def` 或返回 awaitable；Polars、Torch 等计算并行由各自运行库负责。

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
jobs:
  sales_and_wait:
    steps:
      - backend: submit_task
        task: sales
      - backend: wait_task
```

`axonx sales_and_wait --output /tmp/sales.parquet` 提交后等待，两个异步 Step 通过 RuntimeContext 传递 task_id。若需按序执行多个 Task，可继续配置 submit/wait 步骤，或者编写异步 Step 根据上一 Task 的输出组装下一次配置。

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
      - backend: list_tasks
  nightly_status:
    backend: cron
    cron: "0 2 * * *"
    steps:
      - backend: list_tasks
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
        record = await app.run_job("wait", task_id=response.answer["task_id"])
        print(record.answer)
```

远程客户端使用统一的 `list_jobs()` / `run_job()` 接口：

```python
from axonx.components.client import HttpClient, McpClient

async with McpClient(host_ip="127.0.0.1", host_port=1024) as client:
    jobs = await client.list_jobs()
    response = await client.run_job("status")
```

自定义异步 Step 内也可直接使用 Manager：

```python
manager = self.get_component("task_manager", "default")
task_id = await manager.submit("sales", {"output": "/tmp/sales.parquet"})
record = await manager.wait(task_id, timeout=60)
```

所有 Manager 管理方法均为异步。`list_task_ids()` 返回 ID 列表；`get_status(id)` / `wait(id)` / `cancel(id)` 返回单条快照。`wait()` 超时或调用者取消不会取消 Task。`cancel` 会立即终止运行中的 Worker 进程组；`logs` 默认读取最后 64 KiB。

Response.success 表示异步 Job 调用是否成功。查询或等待一个失败 Task 仍是成功的查询，任务结果需检查 `answer.state` 和 `answer.error`。

## 生命周期与状态

状态为 `queued → running → succeeded/failed`；取消完成后进入 `cancelled`。

- FIFO 排队，`max_concurrency` 限制同时运行的 Task 数量。
- `cancel` 会直接取消排队 Task，并用 SIGKILL 立即终止运行中的 Worker 进程组；Manager 负责将最终状态写为 `cancelled`。自行脱离进程组的子进程不在这个保证内。
- Application 正常关闭时先停止异步调用和后台 Job，再取消、等待和清理 Manager 中的全部任务。HTTP 服务默认最多等待现有请求 1 秒（`service.shutdown_timeout`），随后进入清理，长时间 wait 请求不会阻止退出。
- TaskManager 创建 `queued` 状态并处理排队取消；Worker 通过只在父子进程间继承的本地 socket 全量上报运行状态。状态在关闭时原子写入 `<workspace>/tasks/<manager>/state.json`，日志只保留当前进程内最后 1 MiB。Worker 若异常退出且没有上报终态，Manager 会补记为 `failed`。
- 当前按一个常驻 Application 独占一个 workspace 使用。服务被 SIGKILL 或机器异常中止不属于正常关闭保证，可能遗留进程；本版没有独立守护执行服务、远程调度或崩溃恢复。

## 插件

插件通过项目路径配置。`PluginComponent` 对源码计算 SHA-256，在内容变化后构建并安装 wheel；wheel 中的 `axonx.plugins` entry point 用于定位只包含 Task 声明的 `plugin.yaml`。

```yaml
tasks:
  sales: axonx_polars_demo.sales:SalesTask
```

插件只能提供 Task，不参与 Component、Step、Job 注册，也不提供应用默认配置。每次执行都会启动新 Worker 并从已安装文件导入 Task，因此更新插件不会影响正在运行的 Task，后续 Task 无需重启 AxonX 即可使用新版本。

远程节点设置 `components.plugin.default.allow_remote_install: true` 后提供 `POST /plugins`；插件列表通过 `list_plugins` Job 查询。可同时配置 `install_token`。本地使用 `axonx plugin deploy ./plugins/polars-demo --host-ip IP --host-port PORT --token TOKEN` 构建、校验 SHA-256 并上传 wheel。

Polars 示例 `SalesTask` 用合成数据完成加载、聚合、写 Parquet，总收入为 75；不提供 input 时无需外部数据。

硬件采集和远程机器调度尚未实现，可后续通过独立 component 扩展。

## 验证

```bash
pip install -e '.[dev]' -e plugins/polars-demo
python -m pytest -q
```

覆盖真实进程隔离、惰性步骤、失败记录、FIFO、取消/kill/退出清理、等待超时、插件 Polars 执行和真实 CLI/HTTP 调用。
