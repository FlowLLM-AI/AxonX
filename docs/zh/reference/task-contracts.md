# Task 输入输出与持久化协议

本页定义 Task 作者、API 使用者与文件消费者共享的基本契约。研究专属字段见[研究产物协议](research-artifacts.md)；运行语义见[任务生命周期](../concepts/task-lifecycle.md)。以下示例的时间与 run_id 为演示值。

所有持久化 Task 记录统一使用 `version=1`、`task_type=TaskType` 协议头；读取时拒绝缺少版本或不支持的版本。

## 输入与输出基类

BaseInputParams 使用 `extra="forbid"` 和赋值校验。每个 Task 的 input_cls 在基类上声明业务字段。

| 基础输入字段 | 类型与默认值              | 约束                                      |
| ------------ | ------------------------- | ----------------------------------------- |
| task_name    | string 或 null，默认 null | 1–32 个字母、数字、连字符；空串视为未指定 |
| source_tasks | string，默认空串          | 英文逗号分隔合法 Task ID，拒绝重复 ID     |

`source_tasks` 会去除每项周围空白并重新拼接。`source_task(TaskType.X)` 要求指定类型恰好一个上游，不会自动验证目录和产物存在。

BaseOutputParams 使用 `extra="forbid"`、`populate_by_name=True`，基础字段为 `artifacts: dict[str, dict[str, Any]]`，默认空字典。业务扩展字段应由 output_cls 明确声明。

```python
from axonx.task.core import BaseInputParams, BaseOutputParams

class AddInput(BaseInputParams):
    x: int
    y: int

class AddOutput(BaseOutputParams):
    result: int
```

`build_output_params()` 必须返回 output_cls 实例，返回普通 dict 或错误类型会失败。输出只有在执行完成并 prepare_output 后可读。

## 复合 Task 契约

`axonx.task` 导出 `BaseCompositeTask`、`ChildTaskResult` 和 `ChildTaskError`。默认 Task 类型为 `composite`，默认输出模型为 `BaseOutputParams`。自定义复合输出继承 `BaseOutputParams`，只声明业务字段。

父任务的 `metadata.json.children` 是唯一的包含关系记录。每条记录包含 `node_name`、正整数 `attempt`、注册名 `task`、可空 `task_id`、`run_id`、`state`、`exit_code`（0–255）和 `error`。构造失败的调用没有 Task ID。不再使用独立组合文件或组合产物；包含关系与 `source_tasks` 血缘相互独立。参见[复合 Task](../guides/composite-tasks.md)。

## TaskContext

TaskContext 是 frozen dataclass，附着在 Task 上，提供运行时拥有的值：

| 字段              | 类型     | 用途           |
| ----------------- | -------- | -------------- |
| workspace_path    | Path     | 已解析工作区根 |
| registration_name | string   | 定义注册名     |
| task_id           | string   | 目录身份       |
| run_id            | string   | 执行身份       |
| created_at        | datetime | 本轮创建时刻   |
| logger            | 日志对象 | 记录步骤执行   |

插件应读取这些值，不修改运行身份。`task.task_dir` 是 `<workspace>/<type>/<task_id>`；`source_task_dir(id)` 定位同工作区的上游目录。

## TaskDefinition 与 TaskHandle

TaskDefinition 描述可执行定义，字段为 name、source（native/plugin）、plugin（可空）、task_type、description、input_schema、output_schema。description 来自 Task 类的 docstring；缺少或仅含空白时返回空字符串，不阻塞当前 Task 或任务列表。

TaskHandle 是 submit 返回的 immutable dataclass：

```json
{
  "task_id": "base#demo#contract-01",
  "run_id": "a9f248807a0a496abf3738422b379a51",
  "task": "demo"
}
```

字段 `task` 是注册名。这里没有 `task_name` 字段，也没有自动路由到远端的地址。客户端需保留执行机器信息，并以 task_id + run_id 等待这一轮。

## TaskMetadata

`metadata.json` 是从受理到成功、失败或取消的唯一生命周期记录，状态查询返回相同结构。Runner 更新同一个内存记录并原子替换文件；复合 Task 通过该 Runner 发布子调用快照。worker 停止后，管理器读取最新记录，只收敛 Run ID 与 PID 匹配的执行。普通文本日志仍独立保存。

| 字段                                      | 含义                                                      |
| ----------------------------------------- | --------------------------------------------------------- |
| `task_id`、`run_id`、`task_type`          | 目录身份、当前执行身份和类型                              |
| `reg_name`                                | Task 定义注册名                                           |
| `input_params`                            | 类型化输入的 JSON，包含实例 `task_name` 和 `source_tasks` |
| `output_params`                           | 已构建的业务输出，准备完成前为空                          |
| `state`、`exit_code`、`error`             | 当前结果，退出码范围 0–255                                |
| `pid`、`log_path`                         | 所属 worker 与独立文本日志                                |
| `created_at`、`started_at`、`finished_at` | 可空的生命周期时间                                        |
| `steps`                                   | 步骤名、时间与可空的进度百分比（0–100）                   |
| `children`                                | 子调用快照，包含构造前失败的调用                          |

持久化时，非有限浮点数转换为 `null`。非零退出码的失败任务也可能保留 `output_params`；使用者应检查 `state`，再将输出作为成功研究产物使用。共享研究辅助函数 `read_metadata()` 要求 `state=succeeded`，拒绝缺失或未成功的状态；生命周期检查应使用状态查询或 `read_task_metadata()`。不读取或迁移旧状态、组合文件及旧字段。

```json
{
  "task_id": "base#demo#contract-01",
  "run_id": "a9f248807a0a496abf3738422b379a51",
  "task_type": "base",
  "reg_name": "demo",
  "input_params": {
    "task_name": "contract-01",
    "source_tasks": "",
    "x": 1,
    "y": 2,
    "fail": false
  },
  "output_params": {
    "artifacts": {},
    "result": 3,
    "branch": "different",
    "operands": ["x", "y"]
  },
  "children": [],
  "state": "succeeded",
  "pid": 1234,
  "created_at": "2026-01-05T09:00:00+08:00",
  "started_at": "2026-01-05T09:00:01+08:00",
  "finished_at": "2026-01-05T09:00:02+08:00",
  "steps": [
    {
      "name": "finish",
      "started_at": "2026-01-05T09:00:01+08:00",
      "finished_at": "2026-01-05T09:00:02+08:00",
      "percentage": 100
    }
  ],
  "error": "",
  "exit_code": 0,
  "log_path": ".axonx/logs/task.log"
}
```

## Artifact 记录

```json
{
  "artifacts": {
    "dataset": {
      "path": "data/dataset.parquet",
      "size": 10240,
      "sha256": "<64 位十六进制校验和>"
    }
  }
}
```

基类只规定 artifacts 为嵌套映射；path、size、sha256 是标准产物工具生成的记录，研究插件应使用它们。artifact_path() 要求 path 非空、相对 Task 目录且不越界。

不要把工作区根路径写进 artifact path。消费者组合 `<type>/<task_id>/<artifact.path>`，并核对生产插件约定的逻辑名称，例如 dataset、model 或 daily。

`axonx.task.artifact.ArtifactRecord` 统一校验可移植相对路径、字节数和 SHA256；原有 `ArtifactRecord` 导入名是该类型的别名，公开输出映射的 JSON 形状不变。`axonx.task.builtins.stock` 中的 `PortfolioSettings` 统一维护投资组合公共字段及引擎配置转换，插件只覆盖业务默认值和选股规则。

在线发布仍将 `persistent/online/manifest.json` 保存为完整、可独立读取的 v1 历史。新冻结的 `commits/<commit_id>/history.json` 使用 `kind=online_history_node`：仅保存最多 16 个 commit，以及前一个完整分组快照的 Task 相对路径、大小及哈希引用。使用 `read_online_history()` 读取两种表示；已有完整快照仍可读取并作为新节点的前序，不重写旧记录。单独复制冻结节点时必须一并复制其前序依赖，Task 同步会自动包含这些文件。`pin_online_history()` 导出完整 v1 历史及所有引用产物，供独立消费。

新增修订的冻结历史元数据按线性规模增长，当前 manifest 仍包含完整历史。投资组合 Parquet 修订继续保留完整审计报表。消费端按内容摘要独立复制每个不同文件，只在消费任务拥有的副本之间共享存储，因此上游原地写入不会改变已固定的输入；固定输入必须保持不可变。`TaskExecution.output` 直接读取最终状态的输出，不再保留第二份序列化结果。

## 工作区读取与事件

TaskMetadata 使用 run_id 标识一次运行，该字段为必填。

工作区读取会拒绝非法 JSON、错误 task_id/type 和不安全目录，表现为记录缺失。容错读取旨在隔离坏记录，不保证自动修复旧数据。

events.jsonl 是追加进度记录；普通日志在 log_path。写入端先记录进度，再发布匹配 status，终态消费者有机会读取先前事件。其传输投影和最终 result 规则见[事件协议](../api/events.md)。

[Job 与 Task](../concepts/jobs-and-tasks.md) · [Task API](../api/tasks.md) · [研究产物协议](research-artifacts.md)

源码：[输入输出](../../../axonx/task/core/params.py)、[Context](../../../axonx/task/core/context.py)、[定义](../../../axonx/task/catalog/resolver.py)、[Handle](../../../axonx/task/contracts/submission.py)、[状态](../../../axonx/task/storage/workspace.py)、[Metadata](../../../axonx/task/storage/workspace.py)。

## 展示副本

源任务的 `TaskMetadata.replica` 为 null。同步结果包含展示清单：`purpose`、`source_digest`、`policy_digest`、`files`、`omitted`、`source_log_path`。文件记录实际大小和哈希，以及采样行数和日期。源输出和指标保留原值，展示消费者使用实际文件清单。研究输入消费者拒绝副本。

## 并发步骤进度

`BaseTask.report_progress(percentage)` 更新当前执行步骤。`report_progress(name="download", state="running", completed=10, total=100, unit="requests")` 在同一个 `metadata.steps` 列表内更新具名子步骤，`parent` 指向所属执行步骤。metadata 与 `ProgressEvent`（`kind=progress`）共用 `TaskStepStatus`，不另设活动对象、活动事件或存储字段。可选字段包括名称/分组、状态/阶段、计数、计划/截止时间、指标、已提交文件路径和错误。请求完成与有效数据覆盖率分别计量。

Runner 将进度更新和 metadata 发布串行化；具名子步骤计数每秒最多持久化一次，状态/阶段变化及终态立即发布，最终快照保留全部计数。执行步骤返回前须停止并回收后台生产线程。失败、取消及 worker 退出清理会收尾未完成进度，保留已完成工作。窗口结果仍是业务输出，进度不负责发布业务产物或在线 commit。

`children` 是子任务调用生命周期的唯一记录。模型计划来自校验后的输入，界面从子任务记录读取执行状态，从子任务 steps 读取内部阶段。同名子任务目录只保存最新调用，早先 attempt 保留在父记录中；展示同步只捕获每个目录的最新调用。遇到非预期替换 Run 时拒绝同步，不自动替换引用。

Task 声明 `report_kind = "online_pipeline"` 或 `"compare_pipeline"` 选择 Studio 报告；业务索引根据 TaskCategory 分类。在线计划按信号时点组织模型；夜间复核计划使用模型列表，展示公共准备和逐模型阶段。两者都使用 `metadata.steps` 表达进度，使用 `metadata.children` 关联精确 Run，包括嵌套复合任务。`run_task(..., task_name="model-1445")` 显式命名子任务，默认节点名为 `<task_name>-<registration>`；省略 `task_name` 时继承父名称，默认节点名为注册名；生命周期、来源继承和资源回收由框架负责。移除 Activity metadata/事件及独立 live 索引响应，不提供兼容读取；使用这些未发布契约生成的记录需要重建，插件、源服务、接收服务和 Studio 须一起升级。

按组同步的展示副本携带 `replica.snapshot`（来源、父 Task/Run、捕获时间及版本）和 `replica.log`（路径及原始字节范围），保留源状态、清空 PID 且只读。参见[展示同步](../guides/task-sync.md)。

Task 类可独立于 `task_type`、`report_kind` 声明 `category: TaskCategory | None`（`data_update`、`online_prediction`、`comparison`）。定义、排队记录、持久化 metadata 和列表摘要均暴露分类。进程内复合子任务同时记录 `parent_run_id`，业务索引据此隐藏嵌套运行，保留子任务本身的分类。缺失分类及父运行字段时默认 null，不根据 Task 名称猜测旧记录分类。

## 业务时钟与事件回放

`BaseTask(..., clock=...)` 可接收 `WindowClock`，组合子任务继承同一个对象。原有 `axonx.task.contracts.WindowClock` 导入保持有效。时钟控制业务窗口与截止预算；Task 身份、生命周期时间戳、日志和运行性能计时仍使用真实时间。

`axonx.task.clock.ReplayClock(start_at)` 是单驱动虚拟时钟，仅显式 sleep 或 `advance_to()` 推进时间，因此计算期间模拟时间暂停。时间必须带时区且不能倒退。工作线程可读取时钟，只有创建线程可以推进它。多线程插件需使用事件驱动或显式协调等待；仅替换时钟不会加速 `Event.wait`、`Condition.wait`。

`axonx.task.replay` 提供 `ReplaySource`、`ReplayStream`、`ReplayCursor`。`ReplayStream.create(directory, events, context=..., attributes=...)` 复制数据文件到新目录，发布 `stream.json`，不覆盖已有数据集。事件包括 key、带时区的 `available_at`、文件记录（相对路径、大小、SHA256）和插件属性；context 文件固定运行级输入。打开数据流时校验事件顺序、路径和全部文件哈希。转移时需要整个目录，不能只复制 manifest。

`ReplayCursor.wait(deadline, consume, ready)` 推进到事件可用时间，按顺序同步消费，`ready()` 满足后停止。截止时刻及之后的事件不会交付；事件耗尽则推进到截止时间并返回 false。插件负责数据格式、交易日历、校验发布、输入缺失策略和输出隔离。该契约不补造历史返回，也不允许回退到网络补数据；插件须区分还原的窗口快照与原始请求录制，并记录尚未固定的外部依赖。

## 迁移到 AxonX 0.2.1

0.2.1 版本替换旧的 Task 和 Studio 传输契约。框架、Studio 与消费插件应一起
更新。Axon 和 Axon2 要求 `axonx>=0.2.1`，内置 Qlib 插件要求独立版本为 0.2 的
依赖插件。旧 Task 输出需要重新生成，不能混用新旧记录。这些源码修改
不会发布安装包；对应版本发布之前，应使用配套的源码检出安装。

训练模型成员数从注册的模型清单读取，支持多成员集合；展示副本省略
清单时显示不可用。研究和比较列表只保留摘要，选中后加载详情。
