# 参与 AxonX 贡献

[English](CONTRIBUTING.md) · 简体中文

欢迎问题反馈、功能建议、文档改进、研究插件和代码贡献。


应用内部按能力组织文件：机器观察与诊断归 `components/machine/inspection.py`，Task 摘要与血缘归 `components/task_index/query.py`，Job 结果折叠与响应完成边界归 `components/job/response.py`。流水线调用上下文是 `pipeline.py` 的私有实现。Workspace 的路径/浏览、预览和上传分别归 `core.py`、`preview.py`、`uploads.py`；上传暂存通过 `workspace.uploads` 访问。通用、同步与 Task 查询 Step 按能力合并，Task 上下文查询归 Task Step。全部 App 文件职责见 `module-dependencies.md`。

## 开始之前

搜索[已有 Issues](https://github.com/FlowLLM-AI/AxonX/issues) 和相关代码。反馈问题时，请提供复现步骤、预期与实际行为、环境版本，以及已移除凭据的相关日志。提出功能建议时，请说明研究或开发中遇到的问题和期望行为。

新建 Issue 时，使用问题反馈、功能建议或使用问题表单，其他主题可使用空白 Issue。问题反馈请区分已复现故障、间歇性观察和静态分析推测，注明问题范围及本地或远程 target。分享脱敏片段即可，请勿上传整个 `.axonx/` 工作区。

涉及公开 CLI/API/配置契约、持久化任务记录或任务生命周期的较大改动，建议先通过 Issue 讨论设计。每个 PR 聚焦一个完整问题。

## 选择修改位置

| 位置                                              | 职责                                                      |
| ------------------------------------------------- | --------------------------------------------------------- |
| `axonx/`                                          | Application 组装、Component、Job、CLI、服务与 Task 运行时 |
| `plugins/`                                        | 研究 Task、算法、插件 manifest 与插件测试                 |
| `axonx_studio/`                                   | 浏览器 UI、API 客户端、任务表单与研究图表                 |
| `tests/`                                          | 框架单元测试与集成测试                                    |
| `docs/en/`、`docs/zh/`、`docs/figures/`           | 双语指南与共享截图、示意图                                |
| `docs/.vitepress/navigation.mjs`、`github-pages/` | 文档导航、主题与站点构建工具                              |

实现契约见 [Task 开发指南](https://flowllm-ai.github.io/AxonX/zh/dev_guide)、[框架扩展](https://flowllm-ai.github.io/AxonX/zh/development/framework-extensions)和[插件协议](https://flowllm-ai.github.io/AxonX/zh/reference/plugin-manifest)。

## 模块边界

| 模块     | 允许的仓库内依赖                                    | 公开边界                                              |
| -------- | --------------------------------------------------- | ----------------------------------------------------- |
| `utils`  | 无                                                  | 提供 `async_work`、`env`、`logging`、`values`；环境加载必须显式调用 |
| `task`   | `utils.env`、`utils.logging`、`utils.values`        | Task 定义、数据契约、执行和存储                       |
| `plugin` | 无    | 插件发现、安装与 Task 注册信息                |
| `app` | Task 模型/存储接口及注入目录（仅类型导入）、`client`；共享工具 | App 自己维护的常驻组件、Job、传输协议和 Workspace |
| `client` | Task 事件模型；共享工具 | 公开服务契约与调用方维护的 HTTP/MCP 连接 |
| `daemon` | 启动层依赖 App、Task 配置/目录、Plugin 发现和 Client 连接契约；监督器仅依赖标准库 | 守护一个应用服务，创建并回收定时 exec 进程            |
| `cli`    | 其他模块的公开入口                                  | 参数解析、调用路由、结果展示与退出码                  |

Task 模型和枚举不得导入执行、存储或插件代码。Task 执行不导入 App、Plugin 或 CLI。插件发现归 `axonx.plugin.discovery`；`discover_task_registrations()` 只读 Task 注册信息，不计算内容指纹。`axonx.task.runtime.catalog.TaskCatalog` 合并内置注册、检查冲突并按需加载类。CLI 和服务启动层各自装配目录快照；调用方构造根 Task，再调用 `TaskExecutor(resolve_task=resolver).execute(task)`。执行器使用注入的解析器构造和执行子任务，在父任务运行期间绑定执行回调；Task 类不导入执行器，也不持有解析器。

`axonx/task/` 下只保留 `__init__.py` 和五个能力包：

| 包         | 职责                                                     |
| ---------- | -------------------------------------------------------- |
| `models`   | 数据契约、枚举、身份规则和参数校验                       |
| `core`     | Task 编写基类、任务组合、执行窗口和业务时钟              |
| `runtime`  | 任务目录解析、执行、进度、进程控制、生命周期收尾和回放       |
| `storage`  | 工作区布局、元数据、事件与日志文件、产物快照、发布和历史 |
| `builtins` | 具体 Task 和领域实现                                     |

运行时依赖方向为：`runtime` 依赖 `builtins`/`core`/`storage`/`models`，`core` 和 `builtins` 依赖 `storage`/`models`；内置任务还使用 `core` 中的编写基类。Storage 在 Task 内只依赖 models；在线存储中的 `DeadlineBudget` 注解是对 `core.clock` 的纯类型依赖。Task 根包只说明能力包，不执行导入或维护聚合导出；调用方从能力所属模块显式导入。runtime 包入口只加载执行配置，读取配置不会导入执行器；models 包只导出数据契约，不触发执行或存储加载。枚举和身份规则统一归 `task.models.identity`，公共模型策略和日期校验归 `task.models.base`。终止进程和失效运行记录收尾归 `task.runtime.lifecycle`，storage 只提供所需读写。

`task.models` 内部按数据职责组织：

| 模块        | 职责                                       |
| ----------- | ------------------------------------------ |
| `base`      | `TaskModel` 公共策略与日历日期校验         |
| `identity`  | 任务类型、状态、命名和上游任务 ID          |
| `params`    | 参数、结果、训练曲线、预测比较和执行窗口   |
| `artifacts` | 产物引用、协议头、模型集合和回放清单       |
| `lifecycle` | 任务元数据、步骤状态、子任务和展示副本记录 |
| `execution` | 不可变调用身份和子任务结果                 |
| `events`    | 日志片段、进度与日志事件、事件流解析       |
| `reports`   | 在线发布、历史节点及共享回测报告           |
| `query`     | 任务目录、摘要、依赖图和上下文投影         |

契约继承 `TaskModel`，拒绝未声明字段；`Protocol` 显式允许插件扩展载荷，`TaskMetadata` 仍拒绝额外字段。跨字段规则由对应模型校验，这些模块不执行存储或任务操作。直接从所属模块导入模型，不保留已删除模块的兼容别名。

Task 内容按行为和领域归属：共享数据契约归 `models`，任务模板归 `core`，执行与回放驱动归 `runtime`，文件访问归 `storage`，业务专属类型和规则归 `builtins`。`models.lifecycle` 管理调用身份和子任务结果；`models.artifacts.ReplaySource` 描述输入，`storage.replay.ReplayStream` 管理文件快照，`runtime.replay` 管理确定性时间和事件投递。冻结历史格式归 `models.reports.HistoryNode`。来源目录和输入路径校验归 `storage.inputs`，Task 保留编写者使用的薄封装；预测协议组装接收调用方提供的文件版本，不进行 I/O。股票报告契约、信号格式常量及股票专属校验归 `builtins.stock`，通用在线提交不再限制股票格式。展示副本准备、采样、归档规划、传输、索引和应用统一归 `app/components/sync`；内部计划、传输结果和归档应用结果归该目录的 `models.py`。Task 保留展示副本数据契约和只读约束。

### Task 编写与扩展

任务身份由 `task_type`、必填的 `reg_name` 和解析后的 `task_name` 自动确定，构造函数不接受独立的 `task_id`。`upstream_task_ids` 在 Python 输入和 metadata 中统一为有序的 Task ID 数组；CLI 可接收逗号分隔文本或 JSON 数组，在构造任务前转换。生命周期状态只有 `running`、`succeeded`、`failed`；显式终止后的记录按失败收尾。展示选择统一使用 `report_kind`，运营页分别筛选独立推理的 `online`、`online_pipeline`、`compare_pipeline`、`data_update`。metadata 读取直接校验当前结构，不转换旧字段，也不改写原文件。

`task/core` 保留五个文件，直接从所属模块导入类：

| 文件          | 能力                                                                                                         |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| `base.py`     | `BaseTask`、`TaskStep` 和 `ChildTaskError`；输入、身份、子任务调用、输出和运行时回调                         |
| `research.py` | ETL、Analysis、Train、Predict、Backtest 基类，以及逐项发布报告的 `BasePredictionCompareTask`                 |
| `windows.py`  | `BaseWindowTask`、`BaseRealtimeApiTask`、`BaseInferenceTask`；窗口等待、采集轮询、固定模型推理和部分结果发布 |
| `clock.py`    | 真实业务时钟 `WindowClock` 和单调截止预算 `DeadlineBudget`                                                   |
| `__init__.py` | 逐项模块说明、显式子模块导入与 `__all__`                                                                     |

普通任务声明 `input_cls`、`output_cls`，用 `build_task_steps()` 依次 yield 同步方法，用 `build_output_params()` 返回声明的输出模型。步骤生成器是惰性的，后续分支可读取前一步保存的 `self.state`。调用 `report_progress()` 报告进度。`close()` 统一释放资源，包括初始化失败和启动检查被拒绝的情况；清理原始失败时，清理异常不会替换原始异常。`on_failure(error)` 记录业务失败信息，生命周期状态由 执行器 维护。执行器在清理完成后构建输出，因此 `close()` 应保留构建结果所需的数据。

所有 Task 均可在步骤内用 `run_task("registration", **inputs)` 顺序执行子任务，通过 `ChildTaskResult.output_params` 或 `.output` 显式使用结果。条件、循环和重试使用普通 Python。默认失败即停止；`on_error="continue"` 允许继续后续工作，但父任务仍会失败。`children` 返回防御性快照，子任务继承工作区、时区和业务时钟。调用记录使用 `reg_name` 和 `child_task_id`，子任务用 `parent_task_id` 指向调用者；结果通过 `ChildTaskResult.child_task_id` 提供子任务 ID。

输入依赖统一称 upstream/downstream：`BaseInputParams.upstream_task_ids` 是直接上游 Task ID 的有序列表，`upstream_task_id(TaskType.TRAIN)` 要求该类型恰好一个上游。图节点使用 `upstream_task_ids`；上下文关系使用 `direct_upstream`、`all_upstream`（直接及传递上游）和 `direct_downstream`，下游由声明的上游 ID 反向查询得到。parent/child 只表示任务调用，由 `parent_task_id` 和 `children` 记录。同一父任务的子任务之间可以有依赖，但包含关系和调用先后都不会自动生成依赖，应向 `run_task()` 显式传入 `upstream_task_ids=[previous.child_task_id]`。输入依赖不负责调度，也不决定执行所有权。

窗口输入 `ExecutionWindow`、`WindowInputParams` 归 `models.params`；窗口结果 `WindowResult` 与训练曲线、预测对比明细统一归 `models.reports`。通用窗口任务实现 `execute_window(window, budget)`；采集任务实现 `collect(window, budget)`，返回 `None` 时在预算内继续轮询；推理任务实现 `initialize_run()`、`inputs_ready(window)` 和 `infer(window, budget)`，并在初始化时固定非空 `model_identity`。还可以覆盖 `validate_run()`、`window_skip_reason(window)` 和 `build_output_params()` 扩展校验、业务跳过和附加输出；资源仍通过统一的 `close()` 释放。

窗口按开始时间执行；业务跳过、错过窗口、输入超时和截止超时分别保留结果。每个窗口完成或失败后发布元数据，异常会保留前面的结果并停止任务。`incomplete` 和 `skipped` 是业务结果，默认不会使 Task 失败。未提交的结果在截止后返回会变成 `incomplete`；已提交结果按其窗口内的提交时间判断。插件应使用 `budget.remaining_seconds` 限制请求超时和重试，使用 `budget.sleep()` 等待，并在发布前调用 `budget.check()`；预算不能强制中断阻塞请求。

从 `task.runtime.replay` 导入 `ReplayClock`，通过构造参数 `clock=ReplayClock(aware_datetime)` 注入回放时钟；默认使用真实时钟。业务等待、窗口和预算使用该时钟，创建时间、生命周期时间和执行性能计时保持真实。只有创建回放时钟的线程可以推进时间。截止预算和窗口排序按 UTC 时刻处理，覆盖夏令时的重复本地时间。

调用身份和子任务结果分别归 `models.lifecycle.TaskContext` 和 `ChildTaskResult`；上下文不携带 logger 或服务实例，logger 由 Task 持有。任务可在步骤中调用 `publish_output()`，通过可重复调用的 `build_output_params()` 持久化有类型的阶段结果；最终输出仍在清理后构建。模块迁移：`core.task` 改为 `core.base`；`core.standard` 和原 `core.compare` 的预测对比统一归 `core.research`；实时采集和推理从 `core.realtime`、`core.inference` 移入 `core.windows`。原内部 `_WindowTask` 成为公开的 `BaseWindowTask`，窗口资源清理从 `close_run()` 统一改为 `close()`，不保留旧路径兼容模块。

常驻组件留在 App：`components/task_index` 负责轮询、缓存、订阅、血缘图、摘要和事件流，`components/sync` 负责副本准备、传输、索引和应用，`components/updater` 负责应用侧准入和响应完成边界。App 基于 Task 模型和存储接口实现记录查询。服务启动层向 App 注入一个 `task.runtime.catalog.TaskCatalog`。Task 定义 Job 在线程中查询该快照并按需加载类，查询不重新发现插件，也不启动 CLI 子进程。嵌入式调用方通过 `task_catalog=` 显式提供目录以启用定义查询。插件安装、升级或源码修改后重启服务，重新加载定义。Task 执行仍归 `exec`。观察操作不改写 Task 记录；启动检查和显式终止可以收尾已确认本机进程退出的记录。接收归档和查询副本索引无需配置发送组件或同步目标。CLI 不实现常驻组件或 Step。

服务客户端与公开通信契约统一放在 `axonx/client`：`connection.py` 管理连接选项和地址规范化；`constants.py` 管理连接默认值和通信约定；`models.py` 管理 Job 响应、目录和暂存文件结果；`events.py` 管理公开事件流和 Agent 消息补丁，并复用 `task.models.events` 的日志与进度契约。`base.py` 管理连接生命周期、`RemoteServiceError` 和 `RemoteConnectionError`；`http.py` 管理 HTTP/SSE、上传及短生命周期调用；`mcp.py` 管理 MCP 调用。包入口只作命名空间，不主动导入或提供根级转导出。实现从所属模块显式导入，例如 `from axonx.client.http import HttpClient`、`from axonx.client.mcp import McpClient`。App 使用这些契约，保留 Job 执行、事件折叠、鉴权策略、会话及文件操作。Client 不导入 App，单独读取契约不会加载 HTTP/MCP 传输实现。Task 模型与产物协议继续留在 Task。

MCP 使用 FastMCP >=4.1.4 和 MCP SDK >=2.3.0，直接使用当前 SDK 的 snake_case 字段，不保留兼容分支；健康检查验证工具发现能力。

本地 CLI 命令为 `app`、`exec`、`kill`、`plugin`；Task 定义查询统一为服务 Job `list_task_defs` 和 `get_task_def`。根帮助（`axonx`、`--help`、`-h`）保持离线。已有 Daemon 保存了启动 argv，CLI 入口迁移后需要重新启动整个 Daemon。普通 Job 直接连接选定服务，显式远程目标也一样；只有远程原生命令经过 `cli` Job。`exec` 和 `kill` 共用执行配置：CLI 显式字段覆盖 `get_config` 返回值，其余使用模型默认值。只有连接失败会回退，认证、协议和 Job 错误继续传播。配置 Job 返回绝对 workspace/log 路径，并剔除 Cron 运行回调。不再通过 Task 专用环境变量传递执行配置。CLI 保留五个实现模块：`parser.py` 管理命令参数、连接选项、插件语法、cron 校验和离线帮助；`commands.py` 适配本地服务、Task 和插件操作；`remote.py` 调用服务 Job 或透传原始 CLI 命令；`rendering.py` 统一序列化结果和流式事件块；`main.py` 负责路由与异常处理。`__init__.py` 导出 Python 入口和解析接口，`__main__.py` 支持 `python -m axonx.cli`。`Command` 保留解析后的参数与原始参数，因为插件子命令和远程目标需要按各自语法解析。插件与其他命令统一退出策略：输入错误返回 2，操作失败返回 1。

`app/` 一级只有 `__init__.py` 和 `components`、`config`、`core`、`steps`、`workspace` 五个能力包。所有包入口只写职责说明，从所属模块显式导入实现或契约。`core` 负责应用装配、启停和调用分发；`components` 持有能力实现和资源；`steps` 将 Job 调用适配到这些能力。机器指标、构建身份和 Python 执行归 `components/machine`；服务拥有的 CLI 子进程和响应完成回调归 `components/job`。领域数据、枚举和纯校验归各自的 `models.py`，导入模型不能加载执行或传输实现。Provider 查找归 `components/registry.py`，组件分类与依赖声明归 `components/models.py`，共享应用默认值归 `config/defaults.py`。

App 自己维护配置、注册器、Workspace 和启动横幅；Workspace 提供文件操作，不包含 Task 专属的隐藏和删除规则。`command` 命令数组提供外部命令驱动，注入的更新后端负责 prepare/commit/status。`daemon.launcher` 创建一个 Application，并传入明确的 `task.runtime.settings.ExecutionSettings`。顶层 `cron` 列表的每项包含 `expression` 和 `command` 两个字符串，默认 `[]`。定时计划统一使用应用配置的查找、继承、环境变量插值与覆盖规则，继承的列表整体替换。`CronConfig` 校验五字段表达式，并在不调用 shell 的情况下解析 argv。CLI 提供命令校验函数，启动层在启动 Daemon 前检查全部命令，只接受本地 `axonx exec --task NAME`。运行时的 `launch_scheduled` 回调单独传给 `Application`，配置中不包含回调。修改定时配置后重启服务生效，停机期间错过的时间点不自动补跑。

```yaml
cron:
  - expression: "0 16 * * 1-5"
    command: "axonx exec --task download_tushare_task --days-back 7"
```

Daemon 只自动拉起应用服务。手动 CLI 子进程随服务停止，重启不等待命令执行完成，只保留有上限的清理时间。定时 exec 进程由 Daemon 创建、回收，服务重启时继续运行。更新时拒绝新定时启动请求，先停止服务和手动命令，再执行更新，最后启动新服务并重新读取应用配置和定时计划。原地更新不会冻结旧任务后续读取的代码和依赖。`daemon.supervisor` 只使用标准库，接收完整命令、工作目录、环境变量和日志路径，不解释定时规则，也不自动重跑已结束的 Task。

取消安全的异步清理和阻塞工作归 `utils/async_work.py`，由 App、Client 和 Daemon 共用。应用 YAML/JSON 加载、继承和合并归 `app/config`。环境加载和插值归 `utils/env.py`，标量转换统一使用 `utils/values.py`。日志配置、保留清理与参数格式化归 `utils/logging.py`；App 管理清理调度，Task 管理执行日志作用域和日志读取。定时配置模型归 `app/config/models.py`，`components/cron` 只负责调度和生命周期。应用配置定位、继承和覆盖统一使用 `app/config/loader.py::ConfigLoader`；安装的 `axonx.configs` 入口指向包和可选配置文件名。命令行选项语法归 CLI。Workspace 操作直接返回 `app.workspace.models` 中的模型：`WorkspaceListing`、具体的 `FilePreview` 变体、`DeletedEntry`；上传结果使用 `client.models.StagedFile`；目录过滤回调接收 `WorkspaceEntry` 对象。Job 和 HTTP 适配层直接使用结果，在传输边界序列化。

原子写、版本与快照归 `task.storage.files`，在线发布锁归 `task.storage.files`，精确进程识别归 `task.runtime.process`；校验和归 Plugin。App 仅保留上传暂存需要的小型原子写实现。Task metadata 不提供协调锁，同一任务目录的并发变更由调用方串行化。保留在线发布一致性保护和 Daemon 单例锁。模块迁移不提供旧路径兼容导入。

Task 存储按七类能力组织：`files.py` 管理原子写、文件版本、快照和发布锁；`workspace.py` 管理目录布局、生命周期记录和元数据扫描；`artifacts.py` 管理产物引用与校验；`inputs.py` 管理成功上游任务记录、输入及模型集合快照；`logs.py` 提供 `TaskJournal` 和 `TaskLogReader`；`online.py` 管理 `OnlineStore` 与冻结历史链；`replay.py` 管理 `ReplayStream`。包入口逐项介绍并导出全部七个子模块，同时保留共享的 Task 记录操作导出。增量扫描复用未变更记录，遇到不完整记录时保留最后有效缓存并等待重读；文件快照在替换目标之前完成版本检查。已成功上游任务的读取统一使用 `storage.inputs.read_upstream_metadata(workspace, task_id)`，返回任务目录和完整元数据，并校验协议、目录身份、成功状态及展示副本限制。固定输入快照时仍复查来源和产物版本。

## 一、贡献 AxonX 框架

适用于 `axonx/` 中的运行时、CLI、HTTP/MCP 服务、通用扩展点，以及配套的 Studio 和框架测试。研究 Task 和算法请按下面的 Plugin 贡献流程开发。

### 开发环境

Fork 仓库并克隆自己的 fork。在仓库根目录使用 Python 3.12+，本地开发环境支持 macOS 和 Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

Studio 使用 Node.js 22.13+（22.x）、24.x 或 26+，运行：

```bash
cd axonx_studio
npm ci
npm run dev
```

按[快速开始](https://flowllm-ai.github.io/AxonX/zh/getting-started/quickstart)另行启动 Python 服务。代理配置见 [Studio 开发](https://flowllm-ai.github.io/AxonX/zh/development/studio)。文档站要求 Node.js 22+。

### 实现改动

复用已有契约和扩展点。研究算法放在 Task/插件中，框架中的异步资源应保持明确的所有权和清理逻辑。主动变更 CLI 参数、API 响应、配置、任务身份或产物格式时，应同步说明。

测试使用临时工作区。不提交 `.env`、token、私有数据、运行时 `.axonx/` 内容、日志和生成产物。截图中不得包含凭据或私有会话内容。

### 验证

按改动范围选择检查，在 PR 中说明命令和结果。框架 Python 改动先运行相关测试，再按需要运行框架测试集：

```bash
pytest tests/unit/<affected_test_file>.py
pytest tests
```

`pytest tests` 和直接运行 `pytest` 都会排除标记为 `integration` 的测试；后者还会收集因子和策略插件测试，需要先安装对应研究依赖。运行 `pytest -m integration` 前，应准备必要凭据与服务，并检查测试对外部系统的影响。无法运行的检查请说明原因。

Studio 改动在 `axonx_studio/` 中运行：

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

检查相关界面的中英文流程，包括空数据与请求失败。

文档或主题改动在 `github-pages/` 中运行：

```bash
npm ci && npm run build
```

构建会验证渲染页面和 Markdown 导出。根目录及插件 README 和贡献指南由同一构建直接渲染；同步更新中英文，并核查示例命令。

## 二、贡献 Plugin

适用于 `plugins/` 中的研究 Task、因子、模型、策略、回测算法及插件配置。新增研究能力时，优先复用框架的 Task 和扩展点；只有需要通用运行时能力时，再考虑修改 `axonx/`。

### 开发环境

先按框架贡献中的步骤创建 Python 环境、安装主包及开发依赖，再以 editable 模式安装本次开发所需的插件：

```bash
axonx plugin install -e ./plugins/qlib_a158
# 因子和策略层：
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

仓库中的研究插件尚未发布到 PyPI，必须在同一 Python 环境按 Alpha158 → factor → strategy 顺序安装需要的插件及上游依赖。`-e` 需要选定环境中的源码目录，不能与 `--output` 同用；远程部署先构建 wheel，通过 `POST /upload` 上传，再把返回的绝对路径 `location` 传给 `plugin install --target`，并遵循上述依赖顺序。修改 Python 源码后重启常驻服务；依赖或入口点等安装元数据变化后重新安装。

默认 pytest 配置包含因子和策略插件测试及三个插件的源码路径。运行这些测试时，通过上述安装准备研究依赖。插件发现和重启行为见[插件指南](https://flowllm-ai.github.io/AxonX/zh/plugins/management)。

### 实现改动

参考现有插件组织代码，并遵循 [Task 开发指南](https://flowllm-ai.github.io/AxonX/zh/dev_guide)和[插件协议](https://flowllm-ai.github.io/AxonX/zh/reference/plugin-manifest)。新增插件应包含包元数据、插件入口与 manifest、Task 实现、示例配置、测试和中英文 README。

保持任务身份、生命周期、配置和产物格式的兼容性；有意变更时，在文档和 PR 中说明。新增运行时资源时更新 `tool.setuptools.package-data`，确保 wheel 和 sdist 包含这些文件。测试使用临时工作区，研究数据、凭据和实验生成产物不提交到仓库。

### 使用 Agent 开发

外部或内置 Agent 可以结合 [AxonX Skill](skills/axonx/SKILL.md) 与研究 Prompt，开发新插件或优化已有插件。
提供源码仓库、文件／命令工具和选定的执行服务；两条接入路径见 [Agent 总览](docs/zh/agent/overview.md)。
区分插件代码改动、安装与实验执行，Agent 编写的代码遵循相同的贡献检查。

以适配后的 Qlib Alpha158 插件为参考实现，独立的因子和策略插件可以复用兼容的上游代码与产物。
主张研究改进时，记录代码版本、数据快照、训练／评估窗口、参数、成本和 Task ID 和开始时间，遵循[实验设计](docs/zh/research/experiments.md)。
原始执行记录保留在研究环境，公开脱敏后的证据与复现说明。

### 验证

从仓库根目录先运行受影响插件的测试，例如：

```bash
pytest plugins/qlib_factor/tests
pytest plugins/qlib_strategy/tests
```

按实际修改选择命令；涉及框架交互时补充相关框架测试。安装相关研究依赖后，按需要运行 `pytest`。外部服务测试遵循上面的集成测试要求，并在 PR 中说明使用的依赖、验证结果与未运行的检查。主包发布不会发布研究插件，插件的打包和发布需单独处理。

## 两类贡献的共同要求

提交前运行 `pre-commit run --files <changed-files>`，将占位符替换为本次修改的文件路径。文档、PR 和发布要求见下文。

Pre-commit 先用 Ruff 整理 Python 导入，再用 Black 格式化。导入规则统一放在 `pyproject.toml`，仅启用 Ruff 的 `I` 规则。运行 `pre-commit run ruff-check --all-files` 可整理整个仓库的导入。提交前检查并暂存自动修复的内容。

## 文档贡献

修改 `docs/` 下的规范指南，或站点引用的根目录/插件 README 与贡献指南，同步更新中英文。保持相同路径，共享素材放在 `docs/figures/`。站点导航定义位于 `docs/.vitepress/navigation.mjs`。

不修改 `github-pages/.generated/` 或 `github-pages/dist/`，它们会重新生成。站点开发与部署见 [github-pages/README.md](github-pages/README.md)。根目录 README 和贡献指南中的说明变化也应保持双语一致。

## 提交 Pull Request

使用清晰的标题，推荐 Conventional Commits，例如 `fix(tasks): preserve run status` 或 `docs: clarify quick start`。说明问题、改动后的行为、兼容性影响和验证结果。可见 UI 改动附上截图，注明跳过的外部服务测试。

PR 模板会提示这些信息。请列出验证命令和结果，解释未运行检查的原因，并说明中英文文档更新情况。不适用的可选章节可以删除。

贡献遵循项目的 [Apache License 2.0](LICENSE)。

## 发布

主包和 Studio 独立发布。发布前提交版本更新并确保相关 CI 通过；集成测试需要模型 API key，仅在本地按需执行。

- **AxonX**：更新 `axonx/_version.py`，创建并推送 `v<version>` 标签。发布该标签的 GitHub Release 会自动上传 `axonx` 到 PyPI；也可手动运行 `Release / AxonX Python package`，输入不带 `v` 的版本号。
- **Studio**：同步 `axonx_studio/pyproject.toml`、`package.json` 和 `package-lock.json` 的版本，推送到 `main`。手动运行 `Release / AxonX Studio` 并选择 `main` 分支，版本自动读取，不需要标签或版本输入。默认 `both` 先发布 PyPI 再发布 npm；`pypi`、`npm` 可独立发布。npm 标签自动选择：稳定版本使用 `latest`，预发布版本使用 `next`。

AxonX 从发布标签构建；Studio 从手动运行时选定的 `main` 提交构建。两者都校验产物版本。Studio 的 Python/npm 包携带同一份静态资源，预发布版本在 Python 产物中按 PEP 440 规范化。主包发布不会上传研究插件。

打包 CI 还会检查研究插件的 wheel 和 sdist 是否包含全部 Python 模块及 `tool.setuptools.package-data` 声明的数据文件，并逐字节比较它们与源码的内容。添加运行时资源时，请更新 package-data 声明；声明的模式必须能匹配到源码文件。

在 PyPI 为 `axonx` 和 `axonx-studio` 分别配置对应工作流的 Trusted Publisher，环境名为 `pypi`。在 npm 为 `@flowllm-ai/axonx-studio` 配置 `release-axonx-studio.yml` 的 Trusted Publisher，环境名为 `npm`。新的 npm 包需先完成首次发布，再配置 Trusted Publishing。

版本已存在时发布失败，不覆盖或静默跳过。双发中 npm 失败后，优先在原 workflow run 中重跑失败 job，复用同一份产物。也可单包发布；通过新运行补发时应保持 Studio 源码不变。AxonX 发布标签不可移动。
