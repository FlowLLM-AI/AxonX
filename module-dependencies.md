# AxonX 模块依赖明细

核对日期：2026-10-27。本文基于当前工作区代码，包含未提交修改，汇总 `app`、`client`、`cli`、`utils`、`daemon`、`plugin`、`task` 七个包之间的实际依赖。

依赖方向为“具体调用方 → 被依赖的子模块”。表中汇总跨包直接导入，以及 CLI 子进程入口、注入式更新后端两项运行时依赖。Cron 已归入 App 组件，不再是独立包或工作进程。模块路径均省略 `axonx.` 前缀，同包内部导入、第三方库和测试代码不计入跨包明细。函数内导入仍计为直接导入，仅用于类型检查的导入单独注明。

| 模块 | 被依赖的子模块 | 具体调用方 | 主要内容 |
| -------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `utils` | [utils.async_work](axonx/utils/async_work.py) | [app.components.agent.claude.backend](axonx/app/components/agent/claude/backend.py)<br>[app.components.agent.local_session_store](axonx/app/components/agent/local_session_store.py)<br>[app.components.job.command](axonx/app/components/job/command.py)<br>[app.components.proxy.base](axonx/app/components/proxy/base.py)<br>[app.components.sync.local](axonx/app/components/sync/local.py)<br>[app.components.task_index.local](axonx/app/components/task_index/local.py)<br>[app.components.updater.manager](axonx/app/components/updater/manager.py)<br>[app.core.application](axonx/app/core/application.py)<br>[app.steps.sync.steps](axonx/app/steps/sync/steps.py)<br>[app.steps.task.catalog](axonx/app/steps/task/catalog.py)<br>[app.workspace.uploads](axonx/app/workspace/uploads.py)<br>[client.base](axonx/client/base.py)<br>[client.http](axonx/client/http.py)<br>[daemon.launcher](axonx/daemon/launcher.py) | `complete_on_cancel` 和 `run_blocking`；自有异步清理和线程工作完成后再传播取消，由 App、Client 和 Daemon 共用。 |
| `app` | [app.core.application](axonx/app/core/application.py) | [daemon.launcher](axonx/daemon/launcher.py) | 延迟导入 `Application`，直接创建应用并注入更新后端。Workspace 提供通用文件操作，TaskIndex 只读观察记录。 |
| `client` | [client.base](axonx/client/base.py) | [app.components.service.http.app](axonx/app/components/service/http/app.py)<br>[app.components.sync.local](axonx/app/components/sync/local.py)<br>[cli.commands](axonx/cli/commands.py) | 客户端生命周期和远程错误分类；App 与 CLI 直接引用错误类型。 |
| `client` | [client.config](axonx/client/config.py) | [app.components.agent.claude.tools](axonx/app/components/agent/claude/tools.py)<br>[app.components.job.base](axonx/app/components/job/base.py)<br>[app.components.job.command](axonx/app/components/job/command.py)<br>[app.components.service.http.app](axonx/app/components/service/http/app.py)<br>[app.components.service.http.files](axonx/app/components/service/http/files.py)<br>[app.components.service.http.jobs](axonx/app/components/service/http/jobs.py)<br>[app.components.service.http.middleware](axonx/app/components/service/http/middleware.py)<br>[app.components.service.http.service](axonx/app/components/service/http/service.py)<br>[app.config.models](axonx/app/config/models.py)<br>[app.core.banner](axonx/app/core/banner.py)<br>[cli.main](axonx/cli/main.py)<br>[cli.parser](axonx/cli/parser.py)<br>[daemon.launcher](axonx/daemon/launcher.py) | `ConnectionOptions`、地址规范化、连接默认值、环境变量、路由、鉴权头和 SSE 约定；由 Client、CLI 与服务端配置共用。 |
| `client` | [client.events](axonx/client/events.py) | [app.components.agent.base](axonx/app/components/agent/base.py)<br>[app.components.agent.claude.backend](axonx/app/components/agent/claude/backend.py)<br>[app.components.agent.claude.projector](axonx/app/components/agent/claude/projector.py)<br>[app.components.agent.models](axonx/app/components/agent/models.py)<br>[app.components.job.base](axonx/app/components/job/base.py)<br>[app.components.job.command](axonx/app/components/job/command.py)<br>[app.components.job.pipeline](axonx/app/components/job/pipeline.py)<br>[app.components.job.response](axonx/app/components/job/response.py)<br>[app.components.service.http.jobs](axonx/app/components/service/http/jobs.py)<br>[app.core.application](axonx/app/core/application.py)<br>[app.core.dispatch](axonx/app/core/dispatch.py)<br>[app.steps.agent.run](axonx/app/steps/agent/run.py)<br>[app.steps.base](axonx/app/steps/base.py)<br>[cli.remote](axonx/cli/remote.py)<br>[cli.rendering](axonx/cli/rendering.py) | 公开 Job 事件、Agent 消息补丁及统一事件解析；Task 事件继续复用原领域定义。 |
| `client` | [client.http](axonx/client/http.py) | [app.components.machine.inspection](axonx/app/components/machine/inspection.py)<br>[app.components.service.http.jobs](axonx/app/components/service/http/jobs.py)<br>[app.components.sync.local](axonx/app/components/sync/local.py)<br>[app.core.dispatch](axonx/app/core/dispatch.py)<br>[cli.commands](axonx/cli/commands.py)<br>[cli.remote](axonx/cli/remote.py) | `HttpClient`、`run_remote_job`、`stream_remote_job`；远程转发、同步、健康检查和 CLI 调用。 |
| `client` | [client.models](axonx/client/models.py) | [app.components.agent.base](axonx/app/components/agent/base.py)<br>[app.components.agent.claude.backend](axonx/app/components/agent/claude/backend.py)<br>[app.components.agent.claude.tools](axonx/app/components/agent/claude/tools.py)<br>[app.components.job.base](axonx/app/components/job/base.py)<br>[app.components.job.pipeline](axonx/app/components/job/pipeline.py)<br>[app.components.job.response](axonx/app/components/job/response.py)<br>[app.components.service.http.files](axonx/app/components/service/http/files.py)<br>[app.components.service.http.jobs](axonx/app/components/service/http/jobs.py)<br>[app.core.application](axonx/app/core/application.py)<br>[app.core.dispatch](axonx/app/core/dispatch.py)<br>[app.workspace.uploads](axonx/app/workspace/uploads.py) | `JobResponse`、`JobInfo`、`JobCatalog`、`StagedFile`；接口模型只有一份定义。 |
| `app` | [app.config.models](axonx/app/config/models.py) | [daemon.launcher](axonx/daemon/launcher.py) | `ApplicationConfig`、`CronConfig`；统一校验应用配置和定时条目，取得服务、工作区等启动参数。 |
| `app` | [app.config.loader](axonx/app/config/loader.py) | [daemon.launcher](axonx/daemon/launcher.py) | `ConfigLoader.resolve`；解析应用配置来源并合并启动覆盖参数。 |
| `app` | [app.core.banner](axonx/app/core/banner.py) | [daemon.launcher](axonx/daemon/launcher.py) | `print_logo`；在服务启动时显示应用及服务信息。 |
| `cli` | [cli.main](axonx/cli/main.py) | [app.components.job.command](axonx/app/components/job/command.py)<br>[daemon.supervisor](axonx/daemon/supervisor.py) | **运行时子进程调用，无跨包直接导入。** App 的 CommandStep 创建随服务停止的 CLI 子进程，Daemon 只守护一个服务进程，并按服务内 Cron 组件经异步回调发送的 IPC 请求创建独立 exec 进程；这些定时任务跨服务重启继续运行，不自动重跑。 |
| `utils` | [utils.env](axonx/utils/env.py) | [app.config.loader](axonx/app/config/loader.py)<br>[cli.commands](axonx/cli/commands.py)<br>[cli.remote](axonx/cli/remote.py)<br>[daemon.launcher](axonx/daemon/launcher.py) | `load_env` 显式发现、解析并应用 `.env`；`expand_env_vars` 统一处理环境变量插值、默认值和缺失变量检查。 |
| `utils` | [utils.logging](axonx/utils/logging.py) | [app.components.base](axonx/app/components/base.py)<br>[app.components.service.http.files](axonx/app/components/service/http/files.py)<br>[app.components.service.http.shutdown](axonx/app/components/service/http/shutdown.py)<br>[app.components.sync.index](axonx/app/components/sync/index.py)<br>[app.config.loader](axonx/app/config/loader.py)<br>[app.core.application](axonx/app/core/application.py)<br>[app.core.composition](axonx/app/core/composition.py)<br>[app.core.dispatch](axonx/app/core/dispatch.py)<br>[cli.commands](axonx/cli/commands.py)<br>[task.core.base](axonx/task/core/base.py)<br>[task.runtime.executor](axonx/task/runtime/executor.py)<br>[task.runtime.lifecycle](axonx/task/runtime/lifecycle.py) | `get_logger`、日志配置和格式化；同步索引记录无效副本，App、CLI 和 Task 复用共享日志能力。 |
| `utils` | [utils.values](axonx/utils/values.py) | [cli.parser](axonx/cli/parser.py) | `convert_value` 统一 CLI 参数与环境插值的标量转换；`utils.env` 在包内复用同一实现。 |
| `daemon` | [daemon.launcher](axonx/daemon/launcher.py) | [cli.commands](axonx/cli/commands.py) | 延迟导入 `start`；通过 `--config` 统一解析应用配置和顶层 `cron` 列表，使用 CLI 注入的校验函数检查全部命令。`launch_scheduled` 回调单独注入 App，由组合根创建 Cron 组件；Daemon 保存原始启动命令，重启后重新读取配置。 |
| `daemon` | [daemon.client](axonx/daemon/client.py) | [app.components.updater.manager.UpdateManager.request](axonx/app/components/updater/manager.py#L39)<br>[app.components.updater.manager.UpdateManager.status](axonx/app/components/updater/manager.py#L55) | **运行时接口调用，无 App → Daemon 直接导入。** `daemon.launcher` 将 `DaemonClient` 注入应用；App 通过自身定义的 `UpdateBackend` 协议调用 `prepare`、`commit`、`status`，由后端与 Daemon 通信并读取更新状态。 |
| `task` | [task.runtime.catalog](axonx/task/runtime/catalog.py) | [app.core.application](axonx/app/core/application.py)<br>[app.core.composition](axonx/app/core/composition.py)<br>[app.core.context](axonx/app/core/context.py)<br>[cli.commands](axonx/cli/commands.py)<br>[daemon.launcher](axonx/daemon/launcher.py) | `TaskCatalog` 合并内置与外部注册，检查重名、按需解析类并生成定义和 Schema。CLI 与服务启动层分别构建进程内目录快照；App 复用注入目录，执行器接收其 `resolve`。 |
| `plugin` | [plugin.discovery](axonx/plugin/discovery.py) | [cli.commands](axonx/cli/commands.py)<br>[daemon.launcher](axonx/daemon/launcher.py) | `discover_task_registrations` 只读取 Task 名称、类路径和所属分发包，不计算内容指纹。`get_installed_plugin`、`list_installed_plugins` 保留完整安装信息、指纹和故障诊断；两条路径共用清单读取和分发包优先级。 |
| `plugin` | [plugin.installer](axonx/plugin/installer.py) | [cli.commands](axonx/cli/commands.py) | `prepare_artifact`、`install_plugin`、`uninstall_plugin`；准备构建产物、安装和卸载插件。内部使用 `discovery`、`wheel`、`models`；Wheel 处理复用 `manifest` 和 `fingerprint`，pip 安装与卸载统一归 Installer。 |
| `task` | [task.models.events](axonx/task/models/events.py) | [app.components.job.command](axonx/app/components/job/command.py)<br>[app.components.task_index.base](axonx/app/components/task_index/base.py)<br>[app.components.task_index.local](axonx/app/components/task_index/local.py)<br>[app.components.task_index.stream](axonx/app/components/task_index/stream.py)<br>[app.steps.task.query](axonx/app/steps/task/query.py)<br>[cli.remote](axonx/cli/remote.py)<br>[client.events](axonx/client/events.py) | Task 日志和进度契约；Client 组合公开事件流，CLI 和 App 的日志查询继续复用。 |
| `task` | [task.storage.files](axonx/task/storage/files.py) | [app.components.sync.applier](axonx/app/components/sync/applier.py)<br>[app.components.sync.replica](axonx/app/components/sync/replica.py) | `snapshot_file`；准备副本和补齐增量时复用 Task 文件快照能力。 |
| `task` | [task.models.artifacts](axonx/task/models/artifacts.py) | [app.components.sync.index](axonx/app/components/sync/index.py)<br>[app.components.sync.replica](axonx/app/components/sync/replica.py) | `fingerprint`；同步组件根据 Task 和文件元数据计算源版本与快照来源标识。 |
| `task` | [task.models.lifecycle](axonx/task/models/lifecycle.py) | [app.components.sync.local](axonx/app/components/sync/local.py)<br>[app.components.sync.planner](axonx/app/components/sync/planner.py)<br>[app.components.sync.replica](axonx/app/components/sync/replica.py)<br>[app.components.task_index.base](axonx/app/components/task_index/base.py)<br>[app.components.task_index.local](axonx/app/components/task_index/local.py)<br>[app.components.task_index.query](axonx/app/components/task_index/query.py)<br>[app.components.task_index.stream](axonx/app/components/task_index/stream.py) | 同步组件使用 `DisplayReplica`、`LiveSnapshot`、`ReplicaFile`、`ReplicaLog` 和 `TaskMetadata` 描述副本；TaskIndex 使用 `TaskMetadata` 表达运行元数据。 |
| `task` | [task.models.query](axonx/task/models/query.py) | [app.components.task_index.base](axonx/app/components/task_index/base.py)<br>[app.components.task_index.local](axonx/app/components/task_index/local.py)<br>[app.components.task_index.query](axonx/app/components/task_index/query.py) | TaskIndex 使用 `TaskSummary`、`TaskGraph`、`TaskContextSnapshot`；Task 目录在包内复用 `TaskDefinition`、`TaskInfo`。 |
| `task` | [task.runtime.executor](axonx/task/runtime/executor.py) | [cli.commands](axonx/cli/commands.py) | 延迟导入 `TaskExecutor`；CLI 解析注册名并构造 Task，再调用 `TaskExecutor(resolve_task=catalog.resolve).execute(task)`；执行器只为子任务保留注入的解析器，不导入 Plugin。 |
| `task` | [task.runtime.settings](axonx/task/runtime/settings.py) | [cli.commands](axonx/cli/commands.py)<br>[daemon.launcher](axonx/daemon/launcher.py) | `ExecutionSettings`；统一执行字段、默认值与校验。CLI 依次合并 get_config 返回值和显式参数，不读取 Task 专用环境变量；Daemon 复用字段校验。 |
| `task` | [task.storage.logs](axonx/task/storage/logs.py) | [app.components.sync.local](axonx/app/components/sync/local.py)<br>[app.components.sync.replica](axonx/app/components/sync/replica.py)<br>[app.components.task_index.local](axonx/app/components/task_index/local.py)<br>[app.components.task_index.stream](axonx/app/components/task_index/stream.py) | `TaskLogReader`；为副本准备日志，App 本地索引也直接使用同一日志读取能力。 |
| `task` | [task.runtime.lifecycle](axonx/task/runtime/lifecycle.py) | [cli.commands](axonx/cli/commands.py) | 延迟导入 `kill_task`，显式终止本机 Task 并收尾已退出的执行记录。 |
| `task` | [task.storage.workspace](axonx/task/storage/workspace.py) | [app.components.sync.applier](axonx/app/components/sync/applier.py)<br>[app.components.sync.archive](axonx/app/components/sync/archive.py)<br>[app.components.sync.index](axonx/app/components/sync/index.py)<br>[app.components.sync.local](axonx/app/components/sync/local.py)<br>[app.components.sync.planner](axonx/app/components/sync/planner.py)<br>[app.components.sync.replica](axonx/app/components/sync/replica.py)<br>[app.components.task_index.local](axonx/app/components/task_index/local.py)<br>[app.components.task_index.query](axonx/app/components/task_index/query.py)<br>[app.components.task_index.stream](axonx/app/components/task_index/stream.py) | 同步组件复用元数据读取与写入、Task 目录定位、扫描和路径校验；TaskIndex 直接使用 `FileVersion`、`read_entry`、`scan_metadata` 观察任务。 |
| `task` | [task.models.identity](axonx/task/models/identity.py) | [app.components.sync.index](axonx/app/components/sync/index.py)<br>[app.components.sync.local](axonx/app/components/sync/local.py)<br>[app.components.task_index.query](axonx/app/components/task_index/query.py)<br>[app.steps.sync.steps](axonx/app/steps/sync/steps.py)<br>[app.steps.task.query](axonx/app/steps/task/query.py) | App 查询使用 Task 枚举；同步组件和索引 Step 复用任务名称和 ID 校验、名称匹配；Task 目录在包内复用 Task 类型。 |

`utils` 不依赖另外六个包；`task` 的跨包直接依赖只有 `utils.logging`。`plugin` 不依赖 Task 或 App。`app` 的定义查询使用注入的 Task 目录，仅在类型检查时导入目录类型；不直接导入 `plugin`、`cli` 或 `daemon`，通过命令子进程和注入后端与它们交互。`daemon` 对 App、Task 和 Plugin 发现的导入集中在启动装配层，独立监督进程 `daemon.supervisor` 只导入标准库。Client 只依赖 Task 事件数据契约和共享工具，不依赖 App；App 直接使用 Client 的公开连接与通信模型。取消安全工具归 `utils.async_work`。包入口只加载轻量数据契约，`task` 根包只作命名空间；运行时实现从各自模块显式导入。边界测试在全新解释器中检查实际 HTTP/MCP 客户端不会加载任何 App 模块，模型导入也不会触发客户端传输实现。

`task/` 的一级内容只有 `__init__.py` 和 `models`、`core`、`runtime`、`storage`、`builtins` 五个能力包。枚举、身份规则和纯值校验归 models；进程识别、显式终止、失效记录收尾、进度收尾与回放归 runtime。所有 Task 通过执行器在执行期间绑定的回调运行子任务，不再从 core 导入 runtime；解析器只由运行时持有，由同一个执行器递归执行子任务时复用。Storage 不管理进程，在线存储对 `core.clock.DeadlineBudget` 只保留类型检查导入。Task 包内的运行时依赖方向为：`runtime → builtins/core/storage/models`、`builtins → core/storage/models`、`core → storage/models`、`storage → models`。

`task/core` 按编写职责保留五个文件：`base.py` 管理 `BaseTask`、`ChildTaskError`、子任务调用接口、步骤契约与统一的有类型输出发布；调用身份与子任务结果归 `models.lifecycle`；`research.py` 集中标准研究基类和预测对比；`windows.py` 集中通用窗口、实时采集和固定模型推理；`clock.py` 提供真实业务时钟与截止预算，回放时钟和事件驱动归 `runtime.replay`，回放文件访问归 `storage.replay`；`__init__.py` 逐项说明全部直接子模块，显式导入并通过 `__all__` 导出。窗口资源清理复用执行器调用的 `BaseTask.close()`，窗口执行代码不再维护独立清理生命周期。

共享调用身份、子任务结果与持久化状态统一归 `models.lifecycle`；输入参数、窗口输入和输出结构归 `models.params`；训练曲线、预测对比、窗口结果、回测报告及历史节点格式归 `models.reports`。股票报告与信号格式规则归 `builtins.stock`；通用 models 不依赖股票业务。BaseTask 的来源任务和输入路径检查委托 `storage.inputs`。回放输入描述、文件快照、时钟驱动分别归 models、storage、runtime。任务身份集合校验统一归 models。副本准备、采样、归档、传输、索引和应用统一归 `app/components/sync`，内部计划和两种同步结果归该目录的 `models.py`。Task 保留副本数据契约与只读约束；接收和索引入口无需配置发送组件或目标。

任务摘要、排序、血缘图、查询上下文和进度与日志跟踪统一归 `app/components/task_index`，由该组件直接使用 Task 模型与存储接口。

任务关系分为两个独立维度：`upstream_task_ids` 声明输入依赖，TaskIndex 由此构建 upstream/downstream 血缘，并查询 `direct_upstream`、`all_upstream`、`direct_downstream`；`parent_task_id` 和 `children` 记录任务的 parent/child 调用，每条调用记录使用 `reg_name` 和 `child_task_id`，执行器据此管理执行层级，并统一根据自身退出码和全部子任务结果收尾。父子调用和步骤顺序不会自动产生输入依赖。

`async_work` 归 `utils`，Task 日志、进度和产物协议归 Task。公开 Job/Agent 消息与上传结果归 Client；事件折叠、鉴权路由策略、Agent 调用深度和 Workspace 操作归 App。Client 与 App 根包仅作命名空间，不提供旧路径转导出。Workspace 从 `app.workspace.core` 导入，HTTP/MCP 客户端从 `client.http`、`client.mcp` 导入。

执行配置由 `app.steps.common.steps.GetConfigStep` 提供，CLI 通过 `client.run_remote_job` 请求；CLI 显式参数优先于 Job，其次为模型默认值。配置中的 workspace/log 路径在服务端转为绝对路径，Cron 的运行回调不进入 JSON。普通远程 Job 直接通过 Client 请求；远程 exec/kill/plugin 继续通过 CLI 子进程执行。

`app/` 一级只有 `__init__.py` 与 `components`、`config`、`core`、`steps`、`workspace`。所有 App 包入口只包含职责说明。运行时依赖为 `core → components/config/steps/workspace`、`steps → components/config/workspace`、`components → config/workspace`；Pipeline 仅依赖 `steps.base` 接口，具体 Step 由组合根选择。组件对 Application 类型的引用只在类型检查时导入。配置和 Workspace 不反向依赖应用装配或组件实现。领域模型只包含数据、纯校验和纯计算；模型导入不会加载 HTTP、Agent、采集、子进程或存储实现。

机器指标、GPU 探测、远程健康检查、环境诊断、构建身份读取和 Python 执行归 `components/machine`，对应 Step 只适配调用。`BuildInfo`、机器信息和采集结果归该领域的 `models.py`。服务拥有的 CLI 子进程执行与取消清理归 `components/job/command.py`，响应完成回调归 `components/job/response.py`。组件分类、依赖描述和类型校验归 `components/models.py`；Provider 声明、查找和冻结归 `components/registry.py`。Cron 配置模型归 `config/models.py`，统一使用配置加载链；调度循环归 `components/cron`，启动回调单独注入运行时。更新后端接口归 `components/updater/base.py`，Agent 存储接口与记录模型分别归 `session_store.py`、`models.py`，HTTP 请求模型归 `components/service/http/models.py`。

## App 文件职责

以下清单覆盖当前 `axonx/app` 的全部源码和随包资源。所有 `__init__.py` 只说明所属目录的直接子模块，不执行导入或转导出。

### app

| 文件 | 能力 |
| --- | --- |
| [__init__.py](axonx/app/__init__.py) | 说明五个一级能力包和显式导入规则。 |

### core

| 文件 | 能力 |
| --- | --- |
| [core/__init__.py](axonx/app/core/__init__.py) | 说明 core 的直接子模块与能力边界；保持轻量命名空间。 |
| [core/application.py](axonx/app/core/application.py) | 应用对外入口、统一启动顺序、失败回滚、关闭和日志清理调度。 |
| [core/banner.py](axonx/app/core/banner.py) | 启动 Logo、服务地址及运行版本信息的终端展示。 |
| [core/composition.py](axonx/app/core/composition.py) | 内置 Provider 清单、配置驱动的实例化和完整应用装配；按顶层 cron 配置创建调度组件并注入启动回调。 |
| [core/context.py](axonx/app/core/context.py) | 应用实例持有的组件、Job、工作区、更新后端和注入 Task 目录。 |
| [core/dispatch.py](axonx/app/core/dispatch.py) | 调用校验、维护期准入、日志记录和本地/远端 Job 分发。 |
| [core/graph.py](axonx/app/core/graph.py) | 校验组件依赖、检测循环、稳定拓扑排序和依赖注入。 |

### config

| 文件 | 能力 |
| --- | --- |
| [config/__init__.py](axonx/app/config/__init__.py) | 说明 config 的直接子模块与能力边界；保持轻量命名空间。 |
| [config/default.yaml](axonx/app/config/default.yaml) | 内置服务、组件、Job 参数 Schema 和 Step 流水线的默认配置。 |
| [config/defaults.py](axonx/app/config/defaults.py) | 配置模型和运行时组件共用的监听地址与传输预算默认值。 |
| [config/loader.py](axonx/app/config/loader.py) | ConfigLoader 统一处理文件/内置名称/插件入口定位、JSON/YAML 加载、继承、环境展开和覆盖；共享递归合并函数供 Job 使用。 |
| [config/models.py](axonx/app/config/models.py) | 应用、组件、Job、目标服务和 Cron 配置模型；校验五字段表达式并解析命令 argv。 |
| [config/remote.yaml](axonx/app/config/remote.yaml) | 继承默认配置并注入远端服务地址和凭据的配置。 |

### workspace

| 文件 | 能力 |
| --- | --- |
| [workspace/__init__.py](axonx/app/workspace/__init__.py) | 说明 workspace 的直接子模块与能力边界；保持轻量命名空间。 |
| [workspace/core.py](axonx/app/workspace/core.py) | Workspace 的路径边界、目录浏览、删除和预览入口，并持有 UploadStore。 |
| [workspace/models.py](axonx/app/workspace/models.py) | 工作区条目、列表、删除结果及各种文件预览的数据契约。 |
| [workspace/preview.py](axonx/app/workspace/preview.py) | 有界文本、Markdown、JSON/YAML、JSONL、CSV 和 Parquet 预览。 |
| [workspace/uploads.py](axonx/app/workspace/uploads.py) | UploadStore 的名称/目录约束、同步与流式上传、原子发布和幂等清理。 |

### components

| 文件 | 能力 |
| --- | --- |
| [components/__init__.py](axonx/app/components/__init__.py) | 说明 components 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/agent/__init__.py](axonx/app/components/agent/__init__.py) | 说明 components/agent 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/agent/base.py](axonx/app/components/agent/base.py) | Agent 会话与回复接口、指南加载及非流式结果收集。 |
| [components/agent/claude/__init__.py](axonx/app/components/agent/claude/__init__.py) | 说明 components/agent/claude 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/agent/claude/backend.py](axonx/app/components/agent/claude/backend.py) | Claude SDK 的会话生命周期、流式轮次、工具配置及可靠断开清理。 |
| [components/agent/claude/projector.py](axonx/app/components/agent/claude/projector.py) | 把 SDK 实时消息和历史记录转换为稳定的展示块与补丁。 |
| [components/agent/claude/session_store.py](axonx/app/components/agent/claude/session_store.py) | 适配 Claude 会话存储接口，并串行维护会话摘要。 |
| [components/agent/claude/tools.py](axonx/app/components/agent/claude/tools.py) | 把选定 Job 暴露为进程内 MCP 工具，处理目标转发和嵌套深度。 |
| [components/agent/guides/en.md](axonx/app/components/agent/guides/en.md) | 随 Agent 加载的英文工作区开发与操作指南。 |
| [components/agent/guides/zh.md](axonx/app/components/agent/guides/zh.md) | 随 Agent 加载的中文工作区开发与操作指南。 |
| [components/agent/local_session_store.py](axonx/app/components/agent/local_session_store.py) | 本地 JSONL 会话存储、去重、原子摘要、路径约束和取消安全的文件操作。 |
| [components/agent/models.py](axonx/app/components/agent/models.py) | 会话、消息块、存储记录、修改结果和内部调用深度的数据契约。 |
| [components/agent/session_store.py](axonx/app/components/agent/session_store.py) | 后端无关的会话存储接口，包含存在性、记录和摘要操作。 |
| [components/base.py](axonx/app/components/base.py) | 组件身份、应用上下文访问、依赖声明，以及幂等启停和启动失败回滚。 |
| [components/cron/__init__.py](axonx/app/components/cron/__init__.py) | 说明 components/cron 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/cron/scheduler.py](axonx/app/components/cron/scheduler.py) | 解析计划后的下一次触发调度；通过注入回调请求 Daemon 启动进程。 |
| [components/job/__init__.py](axonx/app/components/job/__init__.py) | 说明 components/job 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/job/base.py](axonx/app/components/job/base.py) | Job 输入与系统参数校验、公开策略、Schema 描述和执行接口。 |
| [components/job/command.py](axonx/app/components/job/command.py) | 服务拥有的 CLI 子进程、输出流、退出状态和进程组清理。 |
| [components/job/pipeline.py](axonx/app/components/job/pipeline.py) | 调用上下文、Step 执行计划、顺序流水线、事件背压和取消收尾。 |
| [components/job/response.py](axonx/app/components/job/response.py) | 终态事件折叠，以及响应发送完成后的调用级回调上下文。 |
| [components/machine/__init__.py](axonx/app/components/machine/__init__.py) | 说明 components/machine 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/machine/build_info.py](axonx/app/components/machine/build_info.py) | 读取安装版本、环境变量和 Git 信息，缓存当前进程的构建身份。 |
| [components/machine/gpu.py](axonx/app/components/machine/gpu.py) | 调用 NVIDIA/AMD 工具、解析输出并规范化 GPU 指标。 |
| [components/machine/inspection.py](axonx/app/components/machine/inspection.py) | CPU/内存等机器信息、解释器与工作区诊断、配置目标的健康检查。 |
| [components/machine/models.py](axonx/app/components/machine/models.py) | 构建身份、CPU/内存/GPU、诊断、健康和 Python 执行结果模型。 |
| [components/machine/python.py](axonx/app/components/machine/python.py) | 执行 Python 源码、限制输出、处理超时并回收进程和管道。 |
| [components/models.py](axonx/app/components/models.py) | 组件类型枚举、依赖描述及组件类型名称校验。 |
| [components/proxy/__init__.py](axonx/app/components/proxy/__init__.py) | 说明 components/proxy 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/proxy/base.py](axonx/app/components/proxy/base.py) | 代理接口、错误分类及负责释放上游连接的流式响应。 |
| [components/proxy/http.py](axonx/app/components/proxy/http.py) | HTTP 转发、统一过滤逐跳头、上游错误转换和连接生命周期。 |
| [components/registry.py](axonx/app/components/registry.py) | Provider 名称声明、实现冲突与类型检查、应用级查找和冻结。 |
| [components/service/__init__.py](axonx/app/components/service/__init__.py) | 说明 components/service 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/service/base.py](axonx/app/components/service/base.py) | 对外服务的构建与运行接口。 |
| [components/service/http/__init__.py](axonx/app/components/service/http/__init__.py) | 说明 components/service/http 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/service/http/app.py](axonx/app/components/service/http/app.py) | 装配 FastAPI/MCP、应用 lifespan、路由、中间件和可选 Studio。 |
| [components/service/http/files.py](axonx/app/components/service/http/files.py) | 原始与 multipart 上传路由、请求大小限制、解析器和上传资源释放。 |
| [components/service/http/jobs.py](axonx/app/components/service/http/jobs.py) | 健康、Job 目录、普通调用、SSE 事件和 MCP 工具端点。 |
| [components/service/http/middleware.py](axonx/app/components/service/http/middleware.py) | 协议鉴权，以及 HTTP/MCP 响应发送完成后的更新交接。 |
| [components/service/http/models.py](axonx/app/components/service/http/models.py) | HTTP Job 调用的参数与目标服务请求信封。 |
| [components/service/http/proxy.py](axonx/app/components/service/http/proxy.py) | 将 HTTP 代理路由适配到具名代理组件。 |
| [components/service/http/service.py](axonx/app/components/service/http/service.py) | HTTP 服务配置、规范本机目标地址、Uvicorn 运行和子进程关闭。 |
| [components/service/http/shutdown.py](axonx/app/components/service/http/shutdown.py) | Uvicorn 退出通知、独立于事件循环的关闭期限及强制退出。 |
| [components/service/http/studio.py](axonx/app/components/service/http/studio.py) | 发现和挂载 Studio 静态资源、SPA 回退及资源缺失处理。 |
| [components/sync/__init__.py](axonx/app/components/sync/__init__.py) | 说明 components/sync 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/sync/applier.py](axonx/app/components/sync/applier.py) | 验证归档、补齐增量、校验快照身份，并原子应用或回滚目录替换。 |
| [components/sync/archive.py](axonx/app/components/sync/archive.py) | 生成确定性的压缩归档，并检查文件在归档前后是否变化。 |
| [components/sync/base.py](axonx/app/components/sync/base.py) | 同步组件的 flush 接口。 |
| [components/sync/errors.py](axonx/app/components/sync/errors.py) | 区分源快照变化与确定性的副本预算错误。 |
| [components/sync/index.py](axonx/app/components/sync/index.py) | 源与策略版本、完整副本校验和用于远端对账的索引。 |
| [components/sync/local.py](axonx/app/components/sync/local.py) | 本地同步组件的变化队列、远端对账、轮转调度、限额传输和重试。 |
| [components/sync/models.py](axonx/app/components/sync/models.py) | 文件与批次计划、同步结果，以及统一的 tar 成员空间核算。 |
| [components/sync/planner.py](axonx/app/components/sync/planner.py) | 遍历已发布产物及清单依赖，计算预算并按完整 Task 打包批次。 |
| [components/sync/replica.py](axonx/app/components/sync/replica.py) | ReplicaBuilder 捕获、采样和验证单个副本，并构建身份一致的运行中 Task 组。 |
| [components/sync/sampling.py](axonx/app/components/sync/sampling.py) | 按完整交易日筛选 Parquet 行组，在编码字节限制内写入展示样本。 |
| [components/task_index/__init__.py](axonx/app/components/task_index/__init__.py) | 说明 components/task_index 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/task_index/base.py](axonx/app/components/task_index/base.py) | Task 只读查询、订阅、图、日志和事件跟踪接口。 |
| [components/task_index/local.py](axonx/app/components/task_index/local.py) | 轮询元数据、维护版本和图缓存、共享筛选并返回隔离查询结果。 |
| [components/task_index/query.py](axonx/app/components/task_index/query.py) | 有界摘要、排序、血缘图和 Task 上下文投影。 |
| [components/task_index/stream.py](axonx/app/components/task_index/stream.py) | 合并持久化进度与日志，维护独立游标并拒绝静默切换执行身份。 |
| [components/updater/__init__.py](axonx/app/components/updater/__init__.py) | 说明 components/updater 的直接子模块与能力边界；保持轻量命名空间。 |
| [components/updater/base.py](axonx/app/components/updater/base.py) | 宿主注入的 prepare、commit、status 更新接口。 |
| [components/updater/manager.py](axonx/app/components/updater/manager.py) | 更新准入、维护状态及响应完成后的提交交接。 |

### steps

| 文件 | 能力 |
| --- | --- |
| [steps/__init__.py](axonx/app/steps/__init__.py) | 说明 steps 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/agent/__init__.py](axonx/app/steps/agent/__init__.py) | 说明 steps/agent 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/agent/run.py](axonx/app/steps/agent/run.py) | Agent 轮次、嵌套深度限制、事件转发和终态结果校验。 |
| [steps/agent/sessions.py](axonx/app/steps/agent/sessions.py) | 会话列表、历史、重命名、标记、删除、分叉与取消的调用适配。 |
| [steps/base.py](axonx/app/steps/base.py) | 单次调用状态、类型化具名组件解析和事件发送的 Step 基类。 |
| [steps/common/__init__.py](axonx/app/steps/common/__init__.py) | 说明 steps/common 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/common/steps.py](axonx/app/steps/common/steps.py) | CLI 执行、运行配置、Job 帮助和版本查询的调用适配。 |
| [steps/machine/__init__.py](axonx/app/steps/machine/__init__.py) | 说明 steps/machine 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/machine/steps.py](axonx/app/steps/machine/steps.py) | 机器信息、诊断、健康列表和 Python 执行的调用适配。 |
| [steps/sync/__init__.py](axonx/app/steps/sync/__init__.py) | 说明 steps/sync 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/sync/steps.py](axonx/app/steps/sync/steps.py) | 副本接收、暂存清理、发送 flush 和对账索引的调用适配。 |
| [steps/task/__init__.py](axonx/app/steps/task/__init__.py) | 说明 steps/task 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/task/catalog.py](axonx/app/steps/task/catalog.py) | 查询宿主注入的 Task 定义与参数 Schema。 |
| [steps/task/query.py](axonx/app/steps/task/query.py) | Task 状态、目录、日志、等待、事件流、血缘和上下文查询。 |
| [steps/update/__init__.py](axonx/app/steps/update/__init__.py) | 说明 steps/update 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/update/steps.py](axonx/app/steps/update/steps.py) | Git/Pip 更新、服务重启及更新状态查询的调用适配。 |
| [steps/workspace/__init__.py](axonx/app/steps/workspace/__init__.py) | 说明 steps/workspace 的直接子模块与能力边界；保持轻量命名空间。 |
| [steps/workspace/steps.py](axonx/app/steps/workspace/steps.py) | 工作区列表、预览和删除的调用适配。 |
