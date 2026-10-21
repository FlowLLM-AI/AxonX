# 框架扩展

框架扩展适用于需要新的长生命周期依赖、异步接口步骤或调用编排的场景。研究算法通常写为同步 Task，沿用 [已有开发指南](../dev_guide.md)；不要为纯研究任务引入服务组件生命周期。

![配置到框架装配](../../figures/reference/config-resolution.svg)

## 选择扩展点

| 扩展点        | 典型职责                       | 执行与状态                         |
| ------------- | ------------------------------ | ---------------------------------- |
| BaseComponent | 连接、缓存、外部资源、托管依赖 | _start/_close，应用生命周期        |
| BaseStep      | 调用组件、组合结果、发送事件   | async execute，每次 Job 新实例     |
| PipelineJob   | 顺序组合多个 Step              | 公共 Schema、defaults、最终结果    |
| BaseJob       | 需要自定义事件执行契约         | 自己实现 stream(arguments, system) |
| BaseTask      | 研究数据计算与产物发布         | 同步步骤；submit 可启动 worker     |

Job 是 Application 内的异步编排；Task 的步骤是同步函数。两者的 Step 名称相似，基类与执行边界不同。

Task repository 后端通过 `entries()` 和 `entry()` 返回独立的 `TaskMetadata` 快照。`summaries()` 返回独立的轻量投影，按创建时间和 Task ID 从新到旧排序；应直接从索引投影，不复制完整输入、输出或子调用记录。`put_metadata()` 持久化并索引统一生命周期记录。

## Provider 与局部 registry

`@provider("backend")` 声明类的实现名。框架自带的 axonx 模块会注册为 built-in；外部 Python 类只声明身份，不自动污染全局注册表。嵌入应用需通过 Application(providers=...) 或合法插件 manifest 交给当前应用。

同一 registry 的（类别，backend）不能有不同所有者；相同实现与所有者重复注册可幂等。装配完成后 registry 冻结。名字属于配置契约，不应用类名猜测。

## 可运行的 Component、Step、Job 示例

以下独立脚本在临时工作区创建一个 formatter 组件，通过 Step 读取文本并返回格式化结果，不需要启动 HTTP 服务。

```python
import asyncio
import tempfile
from pathlib import Path
from axonx import Application, BaseComponent, BaseStep, provider
from axonx.components.job import ProgressEvent

@provider("prefix_formatter")
class PrefixFormatter(BaseComponent):
    component_type = "formatter"

    def __init__(self, prefix="AxonX: ", **kwargs):
        super().__init__(**kwargs)
        self.prefix = prefix

    async def _start(self):
        self.logger.info("formatter ready")

    async def _close(self):
        self.logger.info("formatter closed")

    def format(self, text):
        return self.prefix + text

@provider("format_text")
class FormatTextStep(BaseStep):
    async def execute(self):
        formatter = self.get_component("formatter", "default")
        self.response.answer = formatter.format(self.context["text"])
        await self.emit(ProgressEvent(name="formatted", percentage=100))

async def main():
    with tempfile.TemporaryDirectory() as directory:
        config = {
            "workspace_dir": str(Path(directory) / "workspace"),
            "log_dir": str(Path(directory) / "logs"),
            "log_to_console": False,
            "log_to_file": False,
            "components": {
                "formatter": {"default": {
                    "backend": "prefix_formatter", "prefix": "AxonX: "
                }}
            },
            "jobs": {
                "format": {
                    "description": "Format a text value.",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                    "steps": [{"backend": "format_text"}],
                }
            },
        }
        async with Application(
            providers=(PrefixFormatter, FormatTextStep), **config
        ) as app:
            response = await app.run_job("format", {"text": "hello"})
            assert response.success
            assert response.answer == "AxonX: hello"
            print(response.model_dump(mode="json"))

asyncio.run(main())
```

Application 中组件先启动，再启动 Job；关闭反序。Step 在执行时取组件，避免跨请求保存 self.context 或把连接放进模块全局。这里 formatter 已启动才可被调用，Step 自身不承担 _start/_close。

## 声明组件依赖

托管组件之间用 depend 声明，ComponentGraph 校验并注入：

```python
@provider("report_cache")
class ReportCache(BaseComponent):
    component_type = "report_cache"

    def __init__(self, formatter="default", **kwargs):
        super().__init__(**kwargs)
        self.depend("formatter", formatter, PrefixFormatter)

    async def _start(self):
        self.logger.info(self.formatter.format("cache ready"))
```

这段接在前例类定义后；在 providers 中加入 ReportCache 类，并在 components 中配置其命名实例。depend 的 attribute 必须是合法标识符，不能重复；required=true 时必须给实例名。expected base 必须声明非 BASE 类别。依赖缺失、类型不匹配、环路都在启动前失败。

启动失败会回滚已成功启动的资源；关闭会尝试所有资源，不因第一个异常中断清理。_start 中部分分配的资源应能在 _close 中释放，确保失败启动也可回滚。

## 参数、默认值与 system

PipelineJob 使用 RuntimeContext：按 defaults → caller arguments → system 递归合并，再深拷贝执行 context。嵌套覆盖保留未指定的默认字段，列表和标量整体替换，空对象保留已有嵌套字段。公共参数先由 JSON Schema 校验；Schema 内的 default 不自动补齐必填参数。defaults 用于执行 context，不替代公共输入的 required 校验。

```yaml
jobs:
  format:
    parameters:
      type: object
      properties:
        text: { type: string }
      required: [text]
      additionalProperties: false
    defaults:
      internal_mode: simple
    steps:
      - backend: format_text
```

Step 可声明 injected_parameters，用于框架拥有的 system 字段。它们不能与公共 properties 冲突，也不能由 caller 传入。agent_depth 就是内置实例；不应在对外示例中让用户提交它。target 是保留的传输选择字段，不能声明成 Job 业务参数。

## 事件与结果

Step 通过 `await self.emit(...)` 发送 ProgressEvent、LogEvent、ArtifactEvent 或 AgentMessageEvent；通过 self.response 设置 answer、success、metadata。PipelineJob 最后统一生成 ResultEvent，因此普通 Step 不应自行构造重复终态。

默认事件缓冲 64 项；emit 会在缓冲满时等待，实现有界背压。耗时同步计算或文件操作应放线程、Task worker 或其他适合的执行层，避免阻塞应用事件循环。

Step 抛异常会被 pipeline 转为失败结果；设置 success=false 后剩余 Step 不再执行。客户端看到最终 result 才能确定业务结束，见 [事件协议](../api/events.md)。

## manifest 扩展边界

插件可贡献 BaseComponent 类、JobConfig 与 BaseTask。Component 类别必须与声明匹配；manifest 描述 backend，应用配置描述命名实例。

当前插件 loader 用 BaseComponent 校验组件类；BaseStep 只继承 ComponentBase，不能直接通过 manifest components.step 加载。自定义 Step 使用 `Application(providers=...)` 注入。插件 Job 可以组合内置 Step；manifest 的 `components.step` 不支持直接加载 BaseStep 子类。

更多包协议见 [插件 manifest](../reference/plugin-manifest.md)。

## 验证范围

扩展验证应覆盖实际风险：Provider 冲突、依赖缺失/环路、启动回滚、关闭异常聚合、输入 Schema、普通结果与流式终态的一致性，以及断开消费时的资源清理。对研究 Task 另验证 typed input/output、失败状态与产物路径。

新增 backend 后先用最小 Application(providers=...) 验证，再接真实服务、插件环境和 Studio 表单；不要把 UI 能生成表单等同于 Task 研究逻辑已经正确。

实现依据：`axonx/components/base.py`、`axonx/components/registry.py`、`axonx/core/graph.py`、`axonx/core/composition.py`、`axonx/steps/base.py`、`axonx/components/job/pipeline.py` 与 `axonx/components/job/context.py`。

## 实时采集、在线推理与预测比对

`axonx.task.contracts` 导出三个可选的任务编写合同：

- `BaseRealtimeApiTask`（`api`）：实现 `collect(window, budget)`。返回 `None` 继续轮询，或返回状态为 `done`、`skipped`、`incomplete` 的 `WindowResult`。异常记录失败窗口并停止任务。
- `BaseInferenceTask`（`inference`）：在 `initialize_run` 中解析单个模型并设置非空 `model_identity`，实现 `inputs_ready` 和 `infer`。输入等待超时记录 `incomplete`；数据质量、历史新鲜度异常记录 `failed` 并停止任务。初始化时复制模型身份用于审计；插件也必须固定实际 Predictor。
- `BasePredictionCompareTask`（`analysis`）：实现 `compare(key)`，返回 `PredictionComparison`。状态包括 `consistent`、`different`、`protocol_mismatch`、`missing`、`error`。逐项隔离异常，即使单项失败也完成汇总报告。此合同不继承因子分析的 rows/scores。

窗口输入包含按开始时间排序、key 唯一的 `ExecutionWindow`，其 `start_at`、`end_at` 必须带时区，另有正数 `poll_interval_seconds`。等待与耗时使用共享 `WindowClock`，测试可注入假时钟。`DeadlineBudget.remaining_seconds` 使用单调时钟，插件必须据此限制每次请求超时、重试及退避。此工具无法强制中断同步钩子。已错过的窗口标记 skipped；未提交且超过截止时间返回的结果不能标记 done。

插件可实现 `window_skip_reason(window)`，在等待前跳过不适用的业务窗口（例如休市），并在审计记录中保留原始时间安排。

`initialize_run` 获取任务拥有的资源；成功、初始化失败或执行失败后都会调用 `close_run`。清理异常不替代主异常。进程取消仍由现有 worker/task manager 管理，插件不新增进程调度器。

窗口结果、固定模型身份和比对结果直接增量写入 `metadata.json.output_params`，失败时也保留。Runner 原子发布这一份记录，Studio 直接读取它。原有 `manifest.json`、`comparison.json`、`manifest_file` 和 `report_file` 契约已移除，不保留兼容读取。业务数据保存在插件显式目录，先发布数据与元数据，再发布 ready 标记。在线数据发布使用下述不可变存储；质量检查、归一化、交易日历与通知语义由插件负责；AxonX 不新增 Tushare 或模型依赖。

算法验证与模型等价性由研究插件负责。

### 不可变在线提交

通过 `axonx.task.storage.online` 的 `OnlineStore` 发布在线数据。先在临时执行目录准备产物并校验报告，再携带 `DeadlineBudget` 调用 `commit`。新内容复制到 `persistent/online/commits/<commit_id>/`，相同的不可变内容在修订间共享；写入固定的 `history.json` 后，原子替换 `persistent/online/manifest.json`。manifest 替换是唯一提交点。异常或超时保留之前的历史。发布保护只覆盖最终历史检查与 manifest 原子替换，竞争时立即失败；文件准备和报告构建在保护外执行，拒绝覆盖期间产生的新提交。不应在 Task 生命周期之外修改存储。通过 `prepare(commit, history_path)` 回调在发布前构造报告并校验产物。

`OnlineCommit` 记录 Task/Run ID、信号日期/时点、连续修订号、提交时间、固定模型身份、预测协议以及带 SHA256 的产物角色。`OnlineHistory.active(as_of)` 选择信号日期截止范围内的有效修订。历史替换保留原始预测和决策，并使后续组合报告过期，直到重新重放；通过 `report_is_current` 判断。特征和分数选择语义一致时允许模型升级沿用同一策略；组合或特征语义变化需要新的 Task 名称。

已提交的 `WindowResult` 同时携带 `commit_id` 和 `committed_at`。及时完成的原子提交保持 `done`，不会因后续记账跨过截止时间而降为超时；未提交的迟到结果仍为 `incomplete`。若进程在提交和生命周期元数据持久化之间终止，以 manifest 为已提交结果依据。

股票插件通过 `output_params.report` 暴露 `StockOnlineReport`：提交、策略身份、回测维度、日期范围、组合参数、分数选择、评价状态和缺失信号日期。产物角色包括 `predictions`（当次原始分数）、`signal`（当次最终排名）、`signals`（截止日期内的有效排名）、`market`、`calendar`、`input_features`、`prediction_protocol`、`targets`、`orders`、`positions`、`trades`、`daily` 和 `summary`。组合产物沿用股票回测 schema。模拟结果与券商实际成交分开；成熟标签由后续评价处理。即使配置将缺失行情视为停牌，也必须显示缺失信号日期。

将固定历史发布为 `artifacts.signal_history`。消费者通过 `pin_online_history(task, source_id, as_of=...)` 独立复制 manifest 和经过校验的文件，再通过 `online_artifact` 按角色读取。即使最新执行失败，或未发布生命周期元数据就已终止，也以持久化 manifest 为提交依据。重放持久化最终排名，不重新计算历史选股。错过窗口或休市时可以展示前一次提交的报告，并保留其原始日期与 Run ID。

该方案替代 JSONL 信号日志、时段前缀产物名和推理 `ready.json`，不提供兼容读取或转换。旧在线 Task 请使用新 Task 名称重新生成。采集 ready 标记继续作为输入发布协议。组合评价目前重放所选截止日期内的有效历史，不维护增量券商账户。

## 复合 Task 与清理

同步业务顺序、条件和循环使用 `BaseCompositeTask`，通过内置 `submit` Job 只提交父任务。子任务在父任务 worker 内执行，继承父实例名称并保留调用记录。重复调用同一注册名会覆盖终态产物，文件产物应在覆盖前消费。依赖其他 Task ID 的数据时显式传入 `source_tasks`。详见 [复合 Task](../guides/composite-tasks.md)。

插件清单注册 Task；部署配置可以定义轻量 `pipeline` Job 和定时任务：

```yaml
extends: default
jobs:
  refresh:
    backend: pipeline
    defaults:
      task: refresh_data
    steps:
      - backend: submit_task
schedules:
  refresh:
    job: refresh
    cron: "0 16 * * *"
```

共享数据一致性及业务重叠策略由业务 Task 负责；优先使用不可变输入视图，避免在下载和计算期间持锁，共享写入方只保留立即失败的独占保护。复合 Task 不提供分布式锁。调度并发策略只覆盖 Job 调用，提交 Job 在后台 Task 完成前已经返回。TaskManager 监督已受理 worker，并负责停机和取消。取消父 Run 会停止同进程子任务；关闭提交 Job 不会取消已受理的 Task。

维护操作通过 `list_managed_run_ids()` 选择本服务拥有的 worker Run，包括 metadata 已终态或具名 Task 已被替换但进程仍受管理的 worker。暴露共享工作区记录的后端必须覆盖默认的私有后端实现。返回实际进程管理归属，不应根据持久化 metadata 的 PID 推断。

Task manager 实现 `cancel(task_id=None, run_id=None)`，至少提供一个 ID：`task_id` 在 manager 锁内选定当前执行，`run_id` 精确指定某个 Run。同时提供两个 ID 时会校验当前身份，不匹配则返回 false。需要精确清理某次执行时传 `run_id`。

同步 `BaseTask.close()` 在步骤执行后释放资源，包括步骤和初始化失败。清理失败不会覆盖原步骤异常。`on_failure(error)` 可在步骤、输出构造或清理失败时保存业务摘要，失败状态仍由 runner 管理。强制终止进程时不能保证回调执行。

内置 Tushare client 负责关闭自己创建的 session。`retry_rate_limit_forever=True` 按 `rate_limit_retry_seconds` 持续重试频率超限，其他限制仍采用有限重试。`query` 和 `query_has_more` 接收可选 `DeadlineBudget`，限制等待及连接／读取超时，不会把它传给 API。Requests 的超时不保证请求的总耗时，缓慢持续返回的响应可能超过截止时间。收包、JSON 解析、DataFrame 构建和分页合并后检查预算，拒绝超时结果；这些检查不会中断正在执行的网络或计算工作。无截止时间时，频率重试持续到成功或 worker 终止。内置钉钉的 `send_dingtalk_message` 与通知 Task 共用经过校验的环境配置。

## 股票持仓策略

`BaseStockBacktestTask.portfolio_policy()` 向共用股票成交账本提供可选的 `PortfolioPolicy`。插件实现 `replacement_limit(n)` 和 `should_exit(rank=..., age=..., n=...)`；决策只接收当日合格候选排名与已持有的市场日数。引擎在首次建仓后限制每侧实际成交数量，优先退出最差排名，并统一处理报价校验、现金、费用与产物。策略持仓没有固定计划退出日期。 仅在有记录信号的日期评估策略退出；无信号日仍更新估值并处理证券事件。有信号但无合格候选的日期仍以缺失排名评估退出。[Qlib Strategy](../../../plugins/qlib_strategy/README_ZH.md) 使用此扩展。

股票回测插件可向 `run_backtest` 传入可选 `events` 处理器，提供 `successors`、`reset(top_n)`、`apply(date, slot, book, cash, quotes) -> cash`、`blocked(code)` 和 `pending_cash`。引擎遍历 `top_ns`，每个 N 从初始资金、空持仓和重置的事件状态开始，完整重放所有日期。当次执行可修改报价，不影响其他 N。待收款必须有限且非负，计入净值，到账前不能用于买入。引擎在每日估值/交易前调用，并在买入前检查。事件事实及具体证券逻辑保留在插件中；不传处理器时维持原有执行和产物格式。

Scheduler 后端实现 `describe(*, include_history=False, history_limit=20)`，供 `list_schedules` 查询：默认省略历史及最近结果，显式查询时先截取最近历史再复制。TaskManager 提供 `list_restart_blockers()`，通过拥有的 Run ID 和轻量摘要筛选正在排队或运行的定时来源 Task；共享工作区记录本身不表示本服务拥有该 Run。`source` 属于框架执行元数据，必须在 Worker 移交及子 Task 执行中保留。

### 共享工作区与执行归属

工作区仓库列出所有有效 Task 记录，包括其他服务及直接 `exec` 进程写入的记录。读取记录不会接管 worker。`TaskView`（完整列表和详情响应）与 `TaskSummary` 增加仅用于查询的 `managed_run_id`：受管根 Run 指向自身，其精确匹配的进程内子任务指向该根 Run，未受管记录返回 `null`。该字段不写入 `TaskMetadata`。仅当前所选服务管理的活动根 Run 可取消；停止子任务应取消其根 Run。记录进入终态时，worker 仍可能处于清理阶段。

Cron 调度支持 `history_retention_days`（正整数，默认 `7`）。启动及每次写入历史时，从 `schedules/<hash>.json` 移除过期的已结束触发记录，保留运行中的记录。按 `finished_at` 计算时间，旧记录缺少该值时使用 `triggered_at`，无时区的时间按 UTC 解释。该规则替代原先最近 50 次已结束触发的限制，不删除 Task 目录、产物或日志。清理随上述写入执行，不增加独立后台定时器。

每个 cron scheduler 有运行时 `scheduler_id`，并将其写入 Task 的 `source.schedule`。关联当前调度和 Task 历史时应匹配该 ID，不能只匹配名称。持久化记录中的该字段可选，旧记录仍可读取，并显示为未关联当前配置的工作区历史。拒绝未知来源字段的旧版 AxonX，需要先升级才能共享新写入的定时记录。scheduler 的 `running` 和 `last_trigger` 表示当前服务的 Job 调用，不表示已提交后台 Task 的生命周期或结果。`forbid`、`replace` 保持 Job 层语义，不提供跨服务调度去重，也不会取消已经接收的 Task。

维护入口先禁止本实例新的 cron 触发，再检查活动定时 Job 和受管 Run；拒绝维护后恢复触发。当前服务的活动定时 Job 与定时根 Run 即使强制维护也会阻塞。其他服务的磁盘记录不会阻塞维护。服务关闭时，先停止接收新任务并向本服务管理的 worker 进程组发送停止信号，再按依赖逆序等待组件清理。拥有本地子进程的 Task Manager 可以覆盖同步 `request_shutdown(force=False)` 钩子，在等待 Job 或文件清理前阻止提交并发送信号；`force=True` 只能操作已跟踪的 worker 进程组，包括主进程退出后仍存活的后代。该钩子必须非阻塞，并能从信号处理器或关闭 watchdog 线程安全调用。钩子失败不会阻止其他管理器接收停止信号，也不会跳过剩余资源清理。HTTP 服务的 `cleanup_timeout` 限制关闭总时长，再次 Ctrl+C 或超时会强制退出，生命周期记录可能尚未写完。启动及同名提交前，恢复检查稳定的操作系统来源 `machine_id` 与本机匹配或缺少机器标识的非展示副本记录。获取 Task 执行锁并重新核对同一 Run 后，本地管理器仅在记录的 PID 和 `process_started_at` 对应的本机进程实例已退出时，将其标为 failed。缺少机器标识的旧记录只根据执行锁判断，刚创建的 queued 记录保留 5 分钟交接宽限。queued 记录在 worker 交接前保存启动者身份，延迟启动的受理 worker 仍必须匹配其 queued Run。恢复时检查对应子任务的执行锁，保留成功结果，不接管或发送信号给仍存活的 worker。其他机器记录及无法确认的本机进程实例不改动。新身份字段对旧记录可缺省；拒绝未知字段的旧版本需要先升级，才能共享新记录。恢复不重提 Task，也不补放 cron 触发。

本地 runner 在最终状态发布和清理完成前持有 Task 目录建议锁。目录创建、重置、Task 删除、工作区删除和副本应用协调工作区修改；仍被 runner 占用的终态目录不能重置或删除。工作区删除还会保护活动 Task 的文件及其祖先目录。取消操作会等待已开始的队列记录发布及结果收尾完成，再释放对应的修改锁。锁文件位于 Task 目录之外的 `.locks/`，服务使用工作区期间不得移除。这些锁要求文件系统支持共享 POSIX 建议锁，不能替代业务数据锁，也无法约束未参与锁协议的旧版写入方。

更新记录调整为 `updates/<service-key>/<update-id>/`，服务标识由主机名、监听地址、端口和启动目录确定。服务仅恢复自身中断的更新。旧 `updates/<update-id>/` 记录保留在磁盘，不再被修改，也不包含在新的服务级最新状态查询中；仍可按更新 ID 显式读取。

必要的工作区目录变更最多等待 30 秒。`axonx.utils.fs.file_lock` 默认在竞争时立即失败，可选等待必须有限。插件在读取前和成功前比较修订，输入变化时明确失败；生产方必须原子替换文件。

插件环境操作的准入，以及导入与安装协调，最多等待 30 秒；超时只拒绝等待方，不中断当前持有方。
