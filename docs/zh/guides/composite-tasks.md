---
title: 复合 Task
description: 用同步 Python 步骤组合已注册的 Task，显式传递输入并保留独立子任务记录。
---

# 复合 Task

`BaseCompositeTask` 是 `BaseTask` 上的一层薄封装。复合 Task 使用现有接口提交、查询和取消，子 Task 在父 worker 中通过 `TaskRunner` 串行执行，各自保留 Task ID、run ID、status、metadata 和产物。子 Task 共用 worker PID 和日志文件，没有独立受管的 worker。

顺序、循环和条件分支使用普通 Python 表达，不需要额外的 Workflow 服务或配置语言。第一版支持本机同步组合，不提供并行执行、自动重试、崩溃续跑或分布式调度。

## 编写复合 Task

下面的完整示例先相加两个值，再调用内置 `demo` Task 多次翻倍。在插件包中保存为 `example_plugin/chain.py`：

```python
from pydantic import Field

from axonx.task import (
    BaseCompositeOutputParams,
    BaseCompositeTask,
    BaseInputParams,
)


class ChainInput(BaseInputParams):
    x: int
    y: int
    doubles: int = Field(default=2, ge=0)


class ChainOutput(BaseCompositeOutputParams):
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
                source_tasks=previous.task_id,
            )
        self.state["total"] = previous.output["result"]

    def build_output_params(self):
        return self.output_cls(**self.composition_output(), total=self.state["total"])
```

在插件清单中声明：

```yaml
tasks:
  demo_chain: example_plugin.chain:DemoChainTask
```

按[插件开发指南](../dev_guide.md)打包、安装插件，并重启执行服务。以下命令假设执行环境已经安装 `demo_chain`：

```bash
# 本机执行，total 为 20
axonx exec --task demo_chain --x 2 --y 3 --doubles 2

# 或提交给常驻服务，用父 Task 的 handle 等待和取消
axonx submit --task demo_chain --x 2 --y 3 --doubles 2
```

`run_task()` 必须在父 Task 由 `TaskRunner` 执行期间调用。`task` 是已安装的注册名。`node_name` 默认使用注册名，允许字母、数字、下划线和连字符。重复使用节点名会记录新的编号尝试，同一个节点名不能改为另一个 Task 定义。

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

这里的 `download_dataset` 代表具有匹配输入 Schema 的插件 Task。失败会被记录，父 Task 最终仍然为 failed。参数校验和定义查找失败也适用此策略，`KeyboardInterrupt` 和 `SystemExit` 始终向外传播。重复调用不会自动重试或清除之前的失败。扩展复合 Task 时应保留继承的 `exit_code()`，维持这套汇总行为。

无效运行选项，例如不支持的 `on_error` 或冲突的节点定义，会在记录子执行尝试之前抛出 `ValueError`。独占创建子目录后、交接给 Runner 前若准备失败，运行时会关闭子 Task 资源并记录 failed 状态，首次 queued 写入失败也适用此规则。继续执行需要能够持久化失败记录；持续存储错误可能使父 Task 停止。

阶段屏障通过循环边界表达。晚间特征与预测流水线应先跑完全部特征，按时点保存返回结果，再进入预测循环并传入对应结果。业务日期、模型版本等输入应一次确定，再显式传给各子 Task。

## 记录、所有权与取消

父 Task 在执行每个子 Task 前写入 `composition.json`，完成或失败后更新。记录包含格式版本、父 `task_id`／`run_id`，以及子节点名、尝试次数、注册名、可用时的 Task ID、run ID、状态、退出码和错误。running 记录本身不是数据就绪信号；需要时应检查子 Task 状态及其数据协议。

`BaseCompositeOutputParams` 包含 `composition_file`、子执行摘要及带校验和的 `composition` 产物。自定义类型化输出通过 `composition_output()` 加入这些字段。失败即停的父 Task 虽然没有成功 metadata，仍保留组合记录。

包含关系不会自动生成数据血缘边。实际读取上游数据时应显式传入 `source_tasks`。子实例名称由运行时负责，`run_task()` 不接受 `task_name`。名称满足现有 32 字符限制，包含父 run、节点和尝试次数的摘要；运行时独占创建子目录，避免意外替换已有子结果。

通过 TaskManager 取消**父 Task**。共用 worker 停止后，管理器将活动子 Task（包括嵌套复合 Task）收敛为 cancelled；worker 异常退出时收敛为 failed。已经终态的子 Task、替换后的执行和其他进程的执行保持原状态。子 Task 可以使用现有接口查询，但没有独立受管 worker，不能通过 TaskManager 单独取消。`exec` 的取消与终止由调用进程负责，另一个服务无法替该进程收敛子状态。

状态收敛只读取与父 Task ID、run ID 匹配的有效普通组合文件。缺失、损坏、过期、符号链接或其他非普通记录会被忽略，不阻塞父 Task 进入终态；这些记录中的子任务关联无法自动恢复。临时 I/O 错误会向 worker 退出监控传播，以便重试。

在同一执行目标上检查已提交的运行：

```bash
axonx status --task-id '<父 Task ID>'
axonx preview_file --path '<父 Task 类型>/<父 Task ID>/composition.json'
axonx status --task-id '<composition.json 中的子 Task ID>'
axonx cancel --run-id '<父 run_id>'
```

用保存的父 handle 和记录中的子 ID 替换占位符，示例父 Task 的类型为 `base`。输出构建后，父 `status.result.children` 也包含子执行摘要，包括允许子任务失败后继续的 failed 父 Task。失败即停的异常会在输出构建前中止，应检查 `composition.json`。父步骤不包含子 Task 的步骤进度；需要这些细节时查询子状态或订阅子事件流。

固定名称重跑父 Task 仍遵循现有替换行为：旧父目录被替换，使用唯一名称的子目录保留。需要完整组合历史时，应使用不同父实例名称。删除父 Task 不会级联删除子 Task；删除子 Task 也不会更新父记录。

复合 Task 不增加资源锁，也不改变 cron 的重叠策略。共享数据写入仍应显式加锁，当前 Scheduler 的 `forbid` 只覆盖 Job 调用，不覆盖已提交的后台 Task 全生命周期。参见[定时运行](scheduling.md)。

源码：[复合 Task 编写接口](../../../axonx/task/composite.py)、[组合记录](../../../axonx/task/storage/composition.py)、[TaskRunner](../../../axonx/task/runtime/runner.py)。
