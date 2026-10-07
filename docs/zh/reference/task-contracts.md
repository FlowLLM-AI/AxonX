# Task 输入输出与持久化协议

本页定义 Task 作者、API 使用者与文件消费者共享的基本契约。研究专属字段见[研究产物协议](research-artifacts.md)；运行语义见[任务生命周期](../concepts/task-lifecycle.md)。以下示例的时间与 run_id 为演示值。

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

`axonx.task` 导出 `BaseCompositeTask`、`BaseCompositeOutputParams`、`ChildTaskResult` 和 `ChildTaskError`。复合 Task 默认类型为 `base`，子 Task 保留各自定义声明的类型和输入输出契约。

`BaseCompositeOutputParams` 在 `BaseOutputParams` 上增加必需的 `composition_file: str` 和 `children: list[ChildTaskRecord]`（默认空列表）。`composition_output()` 提供这些字段，以及相对路径为 `composition.json` 的 `artifacts.composition` 记录。自定义输出模型在此封装上增加业务字段。

父 Task 拥有的 `composition.json` 包含 `version: 1`、`task_id`、`run_id` 和 `children`。每个子条目记录 `node_name`、正整数 `attempt`、注册名 `task`、可空 `task_id`、`run_id`、`state`、`exit_code`（0–255）和 `error`。构造失败的尝试也会记录，此时没有 Task ID。包含关系独立于 `source_tasks` 血缘。调用方式、失败和取消语义见[复合 Task](../guides/composite-tasks.md)。

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

## TaskStatus

| 字段                                  | 类型/默认                 | 含义                                       |
| ------------------------------------- | ------------------------- | ------------------------------------------ |
| task_id                               | string，必需              | 必须与目录 ID 一致                         |
| run_id                                | 非空 string，必需         | 当前执行身份                               |
| task_type                             | TaskType，必需            | 必须与 ID 中类型一致                       |
| task_name                             | string，默认空串          | 当前实现写入注册名                         |
| config                                | object，默认 {}           | typed input 的 JSON 表示，含实例 task_name |
| state                                 | TaskState，默认 queued    | 当前执行状态                               |
| pid                                   | integer 或 null           | 当时运行进程标识                           |
| created_at / started_at / finished_at | datetime 或 null          | 创建、开始和结束时刻                       |
| steps                                 | TaskStepStatus[]，默认 [] | 已开始步骤快照                             |
| result                                | object，默认 {}           | 构建后的 typed output                      |
| error                                 | string，默认空串          | 错误说明                                   |
| exit_code                             | integer，默认 0           | 0–255                                      |
| log_path                              | string，默认空串          | 独立日志文件位置                           |

TaskStepStatus 包含非空 name、可空 started_at/finished_at、可空 percentage（0–100）。百分比描述当前步骤，不是整项研究进度。

成功状态的简化完整例子：

```json
{
  "task_id": "base#demo#contract-01",
  "run_id": "a9f248807a0a496abf3738422b379a51",
  "task_type": "base",
  "task_name": "demo",
  "config": {
    "task_name": "contract-01",
    "source_tasks": "",
    "x": 1,
    "y": 2,
    "fail": false
  },
  "state": "succeeded",
  "pid": 12345,
  "created_at": "2026-01-05T09:00:00+08:00",
  "started_at": "2026-01-05T01:00:00Z",
  "finished_at": "2026-01-05T01:00:01Z",
  "steps": [
    {
      "name": "finish",
      "started_at": "2026-01-05T01:00:00Z",
      "finished_at": "2026-01-05T01:00:01Z",
      "percentage": 100
    }
  ],
  "result": {
    "artifacts": {},
    "result": 3,
    "branch": "different",
    "operands": ["x", "y"]
  },
  "error": "",
  "exit_code": 0,
  "log_path": ""
}
```

steps 仅展示最后一个步骤，实际 demo 包含更多步骤。日志为空只为避免绑定某个部署路径，真实值由日志系统给出。

失败时关键差异如下，不是独立完整 TaskStatus：

```json
{
  "state": "failed",
  "result": {},
  "error": "RuntimeError: Demo failure requested",
  "exit_code": 1
}
```

非零自定义退出码也进入 failed，但可能已有 result；失败不必然意味着 output 从未构建。取消由管理器记录 cancelled，通常使用退出码 130。

## TaskMetadata

metadata 顶层严格表达成功任务的输入与输出：

```json
{
  "task_id": "base#demo#contract-01",
  "reg_name": "demo",
  "created_at": "2026-01-05T09:00:00+08:00",
  "task_type": "base",
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
  }
}
```

metadata 没有顶层 run_id、state、result 或 error。TaskStatus.result 与 metadata.output_params 对应；任务身份注册名在 metadata.reg_name。

成功过程先构建输出、确定退出码，再写 metadata，然后发布成功 status。非有限浮点数在 metadata 写入时递归转换成 null，以便被 JSON 消费者读取。

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

## 兼容读取与事件

TaskStatus 读取兼容历史字段 execution_id 作为 run_id 的 validation alias。新写入仍使用 run_id；不要同时写两个身份字段或将 execution_id 当成新接口字段。

工作区读取会拒绝非法 JSON、错误 task_id/type 和不安全目录，表现为记录缺失。容错读取旨在隔离坏记录，不保证自动修复旧数据。

events.jsonl 是追加进度记录；普通日志在 log_path。写入端先记录进度，再发布匹配 status，终态消费者有机会读取先前事件。其传输投影和最终 result 规则见[事件协议](../api/events.md)。

[Job 与 Task](../concepts/jobs-and-tasks.md) · [Task API](../api/tasks.md) · [研究产物协议](research-artifacts.md)

源码：[输入输出](../../../axonx/task/core/params.py)、[Context](../../../axonx/task/core/context.py)、[定义](../../../axonx/task/catalog/resolver.py)、[Handle](../../../axonx/task/contracts/submission.py)、[状态](../../../axonx/task/storage/workspace.py)、[Metadata](../../../axonx/task/storage/metadata.py)。
