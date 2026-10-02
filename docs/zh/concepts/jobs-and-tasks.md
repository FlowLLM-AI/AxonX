# Job 与 Task

Job 是 AxonX Application 内的异步能力调用；Task 是有类型输入输出的同步执行单元。它们各有自己的步骤抽象：Job Step 是异步能力步骤，Task Step 是按顺序调用的同步函数。

![提交返回与任务完成](../../figures/concepts/jobs-tasks.svg)

## 对比

| 问题 | Job | Task |
| --- | --- | --- |
| 如何找到 | 配置中的 Job 名，例如 `submit` | 注册名，例如 `demo` |
| 如何执行 | Dispatcher 校验后执行异步 Step | TaskRunner 顺序执行同步 callable |
| 输入契约 | Job 的 JSON Schema 与 defaults | Pydantic input_cls |
| 输出契约 | JobResponse 与可选事件 | Pydantic output_cls 与 metadata |
| 生命周期 | 一次调用的开始到响应 | queued、running、终态及持久记录 |
| 耗时执行 | 可以等待组件或外部 I/O | `submit` 通常在独立 worker 中运行 |

这里的“同步”是函数必须直接执行并返回，不能声明为 `async def`，也不能返回 awaitable。Task 的后台运行来自 TaskManager 启动进程，不是把 Task Step 改成异步函数。

## 从名字到执行身份

```bash
axonx get_task_definition --task demo
axonx submit --task demo --task-name add-check --x 1 --y 2
```

这次调用中：

- `submit` 是 Job 名。
- `demo` 是已注册 Task 定义名，用于解析类与 Schema。
- `add-check` 是用户指定的实例名称。
- `base#demo#add-check` 是 Task ID，对应工作区目录。
- `run_id` 是这一轮执行的标识，由返回的 TaskHandle 给出。

Task ID 不是传给 `--task` 的值。查询某次已运行的实例，应使用 `status --task-id`；查询可执行定义，应使用 `get_task_definition --task`。

## submit 返回了什么

典型响应的关键部分如下，`run_id` 仅为示例：

```json
{
  "success": true,
  "answer": {
    "task_id": "base#demo#add-check",
    "run_id": "a9f248807a0a496abf3738422b379a51",
    "task": "demo"
  }
}
```

这表示 Job 已受理并提交 Task。研究逻辑仍可能失败。例如 `demo --fail true` 的提交可以成功，但 worker 后续会抛出异常，最终为 failed。

应保存完整 handle，然后使用两种身份一起等待：

```bash
axonx wait_task --task-id 'base#demo#add-check' \
  --run-id '<submit 返回的 run_id>' --client-timeout 600
```

`wait_task` 返回终态状态，其 `success` 仅在 Task 为 succeeded 时为 true。固定名称重跑改变 `run_id`，按旧 ID 等待不会悄悄把另一轮执行当成原任务。

## exec 与 submit

```bash
# 当前 CLI 进程运行，不需要先启动 HTTP 服务
axonx exec --task demo --x 1 --y 2

# 已启动服务接收任务，服务机器启动 worker
axonx submit --task demo --x 1 --y 2
```

`exec` 适合插件调试、单次脚本运行和检查参数。`submit` 适合由 Studio 或 API 发起的后台研究，能够配合 TaskManager 的等待、取消和查询。

两种方式都使用 Task 的输入输出契约与工作区记录。`exec` 不把当前进程加入另一个常驻服务的 worker 管理列表；不要依赖常驻服务取消本次 CLI 进程。

## 新增能力时如何选择

若能力是训练模型、转换数据、执行回测，且需要产物与实验身份，通常写 Task。实现 `build_task_steps()` 和 `build_output_params()`，并继承适合的研究契约。

若能力是查询状态、连接远程服务、调用已有组件，或将若干能力组合为公开接口，通常写 Job 与异步 Step。Job 也可以显式调用 `submit`、等待结果，再执行后续步骤；这需要自定义编排逻辑。

不应仅为“后台执行”写 Job 来替代 Task，也不应给每个状态查询制造一个新的研究 Task。

## 相关文档

[任务生命周期](task-lifecycle.md) · [任务管理](../guides/task-management.md) · [Task 契约](../reference/task-contracts.md) · [已有开发指南](../dev_guide.md)

源码：[BaseTask](../../../axonx/task/core/task.py)、[submit 和 wait Step](../../../axonx/steps/task/command.py)、[Job 模型](../../../axonx/components/job/contracts.py)。
