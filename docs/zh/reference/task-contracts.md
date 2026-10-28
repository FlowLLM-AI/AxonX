# Task 契约

## 输入输出基类

从 `axonx.task.core.base` 导入 `BaseTask`，从 `axonx.task.models.params` 导入参数模型。`BaseInputParams` 包含可选 `task_name` 和默认空列表 `upstream_task_ids: list[str]`。名称为 1–32 个字母、数字或连字符，上游 ID 必须规范、唯一且不是当前 Task ID。`BaseOutputParams` 包含产物注册表。

子类声明 `input_cls`、`output_cls`、`task_type`、可选 `report_kind`、同步 `build_task_steps()` 和有类型的 `build_output_params()`。执行器管理 metadata/进度，在最终输出构建前调用 `close()`。`publish_output()` 校验并保存部分结果，`report_progress()` 只在执行期间可用。

## 子任务契约

所有 BaseTask 都支持 `run_task(reg_name, *, node_name=None, on_error="stop", task_name=None, **inputs)`，返回包含 record、success、child_task_id、可选有类型 output_params 和 JSON output 的 `ChildTaskResult`。构造失败可能没有子任务 ID 或输出，读取不可用输出会抛错。

子任务默认继承父名称并在同一进程执行。调用记录包含 node_name、attempt、reg_name、child_task_id、started_at、state、exit_code、error。on_error=continue 不会自动使父任务成功。父子调用与上下游输入依赖独立，没有独立的 composite Task 类型。

## TaskContext

不可变 dataclass 包含 workspace_path、registration_name、task_id、created_at、timezone、可选 parent_task_id 和 execution_target，不提供应用客户端或组件。

## Task 定义

`TaskInfo` 包含 name、source、plugin、task_type、description，`TaskDefinition` 增加 input_schema、output_schema。定义属于目录快照，不是执行句柄。CLI exec 输出业务结果并返回进程退出码。

## TaskMetadata

完整文档将协议版本/类型、当前身份、进程所有权和业务结果保存在一起：

| 字段                                | 含义                            |
| ----------------------------------- | ------------------------------- |
| task_id、reg_name                   | 目录和注册身份                  |
| started_at                          | 当前执行身份，重跑时改变        |
| state、exit_code、error             | running/succeeded/failed 及结果 |
| machine_id、pid、process_started_at | 可验证的进程身份                |
| execution_target、workspace_dir     | 可选的源机器远程路由信息        |
| parent_task_id、children            | 调用关系                        |
| created_at、finished_at、log_path   | 时间和日志位置                  |
| input_params、output_params         | 校验后的业务数据                |
| steps                               | 步骤快照                        |
| replica                             | 可选展示副本信息                |

同名执行覆盖当前记录和输出，保留 persistent/，写入由调用方协调。观察不修复失效记录。`wait_task` 捕获 started_at，等待期间遇到替换会拒绝继续。

## 直接用 Python 执行

```python
from pathlib import Path
from axonx.task.builtins.demo import DemoTask
from axonx.task.runtime.executor import TaskExecutor

metadata = TaskExecutor().execute(DemoTask(
    {"task_name": "python-check", "x": 1, "y": 2},
    workspace_path=Path(".axonx"),
    reg_name="demo",
))
assert metadata.exit_code == 0
print(metadata.task_id, metadata.started_at, metadata.output_params)
```

执行子任务时需向 TaskExecutor 提供解析器；CLI 根据已安装插件构造目录并传入 resolve 方法。

## 产物记录

文件记录包含相对 path、size 和 revision，路径必须位于 Task 目录内。共享模型位于 `models.artifacts`，研究结果位于 `models.reports`。用 `storage.inputs` 核验并固定上游产物。原子发布 metadata 不保护目录免受并发写入。

## 工作区读取与事件

`task_index` 提供观察。ProgressEvent 扩展步骤状态，LogEvent 扩展有界字节日志块；Job 事件还包括 artifact、agent_message、result，详见[事件](../api/events.md)。

## 展示副本

副本记录源/策略修订、采样或省略文件和可选活动父任务快照。LiveSnapshot 包含 source_id、root_task_id、root_started_at、captured_at 和有序 revision。副本不能执行，也不应作为可修改的研究源。

## 业务时钟与事件回放

BaseWindowTask、BaseInferenceTask 位于 `core.windows`，WindowClock/DeadlineBudget 位于 `core.clock`，ReplayClock 位于 `runtime.replay`。生命周期计时仍为真实时间，窗口业务结果与 Task 状态独立。回放或报告前核验并固定在线历史，详见[研究产物](research-artifacts.md)。

源码：[开发接口](../../../axonx/task/core/base.py)、[模型](../../../axonx/task/models/lifecycle.py)、[执行器](../../../axonx/task/runtime/executor.py)。
