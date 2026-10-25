---
title: 复合 Task
description: 用同步 Python 步骤组合已注册的 Task，显式传递输入并保留独立子任务记录。
---

# 复合 Task

`BaseCompositeTask` 是 `BaseTask` 上的一层薄封装。复合 Task 通过 exec 执行，并使用只读接口查询，子 Task 在父 worker 中通过 `TaskRunner` 串行执行，每次调用拥有新的 Run ID。每个注册名默认使用父任务解析后的 `task_name` 构造 Task ID，并保存统一 metadata 和产物；重复调用同一注册名会覆盖该目录中的终态产物。子 Task 共用 worker PID，但每个 Run 拥有独立日志文件；父任务日志也包含其嵌套子任务的日志。子 Task 没有独立受管的 worker。已完成任务的日志流读取有限的日志快照后结束，即使旧任务共用的进程日志仍在增长，也不会继续等待。 Run 日志遵循统一的 7 天保留策略，运行中的 Run 日志不会被清理。

顺序、循环和条件分支使用普通 Python 表达，不需要额外的 Workflow 服务或配置语言。第一版支持本机同步组合，不提供并行执行、自动重试、崩溃续跑或分布式调度。

同名重跑清理当次执行文件（包括 metadata.json 和 events.jsonl），但保留约定的 `persistent/` 目录。通过 `self.persistent_dir` 保存累计业务数据；插件负责其格式、更新和并发控制。Run ID 和生命周期记录仍只描述当前执行。显式删除 Task 会一并删除持久数据；展示同步以所选产物原子替换目标 Task 目录。`persistent/` 必须是普通目录，不能是符号链接。

## 编写复合 Task

下面的完整示例先相加两个值，再调用内置 `demo` Task 多次翻倍。在插件包中保存为 `example_plugin/chain.py`：

```python
from pydantic import Field

from axonx.task import BaseOutputParams, BaseCompositeTask, BaseInputParams

class ChainInput(BaseInputParams):
    x: int
    y: int
    doubles: int = Field(default=2, ge=0)

class ChainOutput(BaseOutputParams):
    total: int

class DemoChainTask(BaseCompositeTask):
    """先相加两个值，再按配置次数翻倍。"""

    input_cls = ChainInput
    output_cls = ChainOutput

    def build_task_steps(self):
        yield self.run_chain

    def run_chain(self):
        previous = self.run_task(
            "demo", node_name="sum", x=self.input_params.x, y=self.input_params.y
        )
        for index in range(self.input_params.doubles):
            total = previous.output["result"]
            previous = self.run_task(
                "demo",
                node_name=f"double-{index}",
                x=total,
                y=total,
            )
        self.state["total"] = previous.output["result"]

    def build_output_params(self):
        return self.output_cls(total=self.state["total"])
```

在插件清单中声明：

```yaml
tasks:
  demo_chain: example_plugin.chain:DemoChainTask
```

按[插件开发指南](../dev_guide.md)在执行环境中打包、安装插件，新的 exec 进程会加载安装后的代码。以下命令假设执行环境已经安装 `demo_chain`：

```bash
# 本机执行，total 为 20
axonx exec --task demo_chain --x 2 --y 3 --doubles 2

```

`run_task()` 必须在父 Task 由 `TaskRunner` 执行期间调用。`task` 是已安装的注册名。`node_name` 默认使用注册名，允许字母、数字、下划线和连字符。重复使用节点名会记录新的编号尝试，同一个节点名不能改为另一个 Task 定义。节点名和调用序号只标识调用记录，不影响 Task ID 或目录。

返回的 `ChildTaskResult` 提供 `task_id`、`run_id`、`success`、`record`、`output_params` 和 `output`。`output_params` 保留子 Task 声明的 Pydantic 类型，`output` 为 JSON 模式的字典。构造或参数校验失败时没有 Task ID；输出构建前发生异常时没有输出。允许失败后继续时，应先检查 `success` 再读取结果。

`children` 和返回结果中的 `record` 都是防御性快照，修改它们不会改变父 Task 的记录状态。`task`、`node_name`、`on_error` 和 `task_name` 由 `run_task()` 保留，子 Task 的业务输入应使用其他字段名。

## 失败策略与阶段屏障

默认 `on_error="stop"`：子 Task 抛出异常或返回非零退出码时，抛出 `ChildTaskError`，异常保留 `result`，后续工作停止。

需要尝试所有子 Task 的批次可以使用 `on_error="continue"`：

```python
for dataset in datasets:
    result = self.run_task(
        "download_dataset",
        node_name=dataset,
        on_error="continue",
        dataset=dataset,
    )
    if not result.success:
        self.logger.warning(result.record.error)
```

这里的 `download_dataset` 代表具有匹配输入 Schema 的插件 Task。失败会被记录，父 Task 最终仍然为 failed。参数校验和定义查找失败也适用此策略，`KeyboardInterrupt` 和 `SystemExit` 始终向外传播。重复调用会覆盖同名子任务的终态产物，但不会自动重试或清除之前的失败记录。扩展复合 Task 时应保留继承的 `exit_code()`，维持这套汇总行为。

无效运行选项，例如不支持的 `on_error` 或冲突的节点定义，会在记录子执行尝试之前抛出 `ValueError`。交接给 Runner 前若组合记录准备失败，运行时会关闭子 Task 资源并记录失败调用，不创建子状态目录。Runner 从调用入口接管资源，目录检查或初始状态发布失败也会关闭资源。目录准备完成后，存储允许时持久化失败状态；被拒绝的已有执行保持原状。继续执行需要能够持久化失败记录；持续存储错误可能使父 Task 停止。

文件型特征与预测批次应在同一个时点循环内执行特征及对应预测，在下次特征调用覆盖文件前消费产物。保存 `ChildTaskResult` 只保留类型化输出快照，不会复制文件。需要独立的逐时点产物时，应使用不同 `task_name` 分别运行父 Task。业务日期、模型版本等输入应一次确定，再显式传给各子 Task。

## 记录、所有权与取消

Runner 在执行期间持续写入 `metadata.json`。父 Task 在每个子任务启动前、完成或失败后更新 `children`，其中记录节点名、调用序号、注册名、可空 Task ID、Run ID、状态、退出码和错误。running 记录本身不是数据就绪信号；应检查子任务状态和产物协议。

复合 Task 默认输出为 `BaseOutputParams`。自定义输出继承该模型，声明并正常返回业务字段；子调用记录只保存在顶层 `metadata.json.children`。失败和取消的父任务也保留该记录，包括尚未构建业务输出的失败即停场景。

包含关系不会自动生成数据血缘边。实际读取不同 Task ID 的上游数据时应显式传入 `source_tasks`。每个子 Task（包括嵌套复合 Task）默认继承父 Task 解析后的 `task_name`，`run_task(..., task_name="instance")` 可显式指定独立实例。运行时不会在名称中追加摘要、节点名或调用序号。重复调用同一注册名会复用 Task ID，通过 `TaskRunner` 覆盖终态产物；活动或无法识别的目录会被拒绝。每次调用生成新的 Run ID。Task 不能将自身 ID 作为上游，构造阶段会在提交或执行覆盖文件前拒绝这种调用。调用记录保留状态和错误，但覆盖后旧 Run 的状态与产物不再可用。即使父 Task 注册名不同，同名父 Task 仍共享子目录。共享固定名称的流程需要串行执行；覆盖不保留旧 Run，也不提供失败回滚。

Runner 负责正常完成和中断清理。强制终止 exec 进程后，观察会收敛确认已退出的本机 Run；外机与无法验证的记录保持原样。

在同一目标上检查执行记录：

```bash
axonx status --task-id 'composite#demo_chain#<name>'
axonx read_task_log --task-id 'composite#demo_chain#<name>' --offset -1
```

从 `metadata.json.children` 读取子 Task ID。纯复合 Task 默认类型为 `composite`，目录如 `composite/composite#demo_chain#<name>/`；子类可使用专用类型。父步骤不包含子 Task 的步骤进度，应查询各子 Task 的状态或事件流。

固定名称重跑父 Task 会替换旧父目录；各阶段执行时覆盖对应子目录；新运行跳过的子实例仍留在磁盘，但不会出现在新组合记录中。已有子目录及此前位于 `base` 的父目录不会自动迁移。需要完整组合历史时，应使用不同父实例名称。删除父 Task 不会级联删除子 Task；删除子 Task 也不会更新父记录。

复合 Task 不增加资源锁。定时 exec 进程可以重叠执行；调用者必须串行处理共享 Task 目录与数据写入。参见[定时运行](scheduling.md)。

源码：[复合 Task 编写接口](../../../axonx/task/core/composite.py)、[组合记录](../../../axonx/task/schemas/lifecycle.py)、[TaskRunner](../../../axonx/task/runtime/runner.py)。

子任务默认继承父 task_name；需要独立模型实例时，使用 `run_task("predict", task_name="model-1445", ...)` 显式指定。节点名称只标识调用记录，不能替代实例名称。
