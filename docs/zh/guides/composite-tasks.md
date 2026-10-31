# 组合任务

任何 BaseTask 都可同步调用已注册子任务。条件、循环和阶段屏障属于父任务，不需要专用组合基类或 Task 类型。

## 编写父任务

```python
from axonx.task.core.base import BaseTask
from axonx.task.models.params import BaseOutputParams

class ChainOutput(BaseOutputParams):
    total: int

class DemoChainTask(BaseTask):
    """Run two registered additions in one execution process."""
    output_cls = ChainOutput

    def build_task_steps(self):
        yield self.first
        yield self.second

    def first(self):
        result = self.run_task("demo", node_name="first", task_name="first", x=1, y=2)
        self.state["first"] = result.output["result"]

    def second(self):
        result = self.run_task("demo", node_name="second", task_name="second",
                               x=self.state["first"], y=4)
        self.state["total"] = result.output["result"]

    def build_output_params(self):
        return ChainOutput(total=self.state["total"])
```

在 plugin.yaml 注册 `demo_chain: example_plugin.chain:DemoChainTask`，然后执行 `axonx exec --task demo_chain --task-name experiment`，结果为 7。子任务共享父进程和工作区。示例显式设置子实例名；生产流水线需要隔离实验输出时应从父名称派生子名称。

## 失败与阶段屏障

`run_task` 在子任务完成后返回，检查 result.success、child_task_id、record 和 output。默认 on_error=stop 抛出 ChildTaskError；continue 保留失败记录并可继续后续工作，但父任务默认退出策略仍报告失败。只有明确处理了执行错误才应覆盖 exit_code；正常完成的业务结论保留在输出字段中。

输入依赖需要显式传 upstream_task_ids，父子包含关系不建立这些边。node_name 标识调用和尝试，task_name 选择目录。重复调用同注册/名称会替换当前输出，应先消费或固定产物。

## 记录、所有权与停止

父 metadata.children 保存调用快照，构造失败可能没有子 ID。子任务有独立 metadata，但共享进程所有权。`kill` 将活动子任务解析到根所有者并停止执行进程及后代，不能独立停止进程内子任务而保留父执行。

独立实验使用不同父/子实例，固定名称流水线由调用方协调。启动或显式 kill 修正确认已退出的本机记录，查询保持只读。

[Task 契约](../reference/task-contracts.md) · [生命周期](../concepts/jobs-and-tasks.md)
