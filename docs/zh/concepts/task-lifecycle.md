# 任务身份与生命周期

Task ID 标识工作区中的一个任务目录，`run_id` 标识一轮执行。提交受理、执行终态和成功产物发布是不同阶段；正确判断结果需要保存提交返回的 handle，并核对最终状态。

![Task 生命周期](../../figures/concepts/lifecycle.svg)

## 三种名字与一个运行标识

| 字段            | 含义                     | 示例                  |
| --------------- | ------------------------ | --------------------- |
| Task 注册名     | 查找定义与输入 Schema    | `demo`                |
| input.task_name | 用户给实例指定的名称     | `trial-01`            |
| task_id         | 类型、注册名和实例名拼接 | `base#demo#trial-01`  |
| run_id          | 每次执行独立生成的标识   | UUID 的十六进制字符串 |

`task_name` 允许 1–32 个英文字母、数字或连字符。省略或传空字符串时，框架使用包含小时级时间前缀和随机后缀的名称。Task ID 中的 `#` 必须保留，shell 中应使用引号。

统一记录使用 `metadata.reg_name` 保存定义注册名，使用 `metadata.input_params.task_name` 保存解析后的实例名。新记录还持久化执行机器的稳定 `machine_id` 和进程实例启动时间 `process_started_at`；queued 阶段保存启动者身份，worker 接手后更新。服务启动及同名提交前，将确认已中断的本机 Run 收尾为 failed。缺少机器标识的旧记录在执行锁空闲时自动判失败，刚创建的 queued 记录保留 5 分钟交接宽限。其他机器记录保持原样。恢复边界见[日志排障与备份恢复](../guides/operations.md)。

## 状态含义

| state     | 含义                               | 是否终态 |
| --------- | ---------------------------------- | -------- |
| queued    | 已受理，等待 worker 交接或运行     | 否       |
| running   | 正在执行同步步骤                   | 否       |
| succeeded | 步骤与输出完成，退出码为 0         | 是       |
| failed    | 异常、非零退出码或异常 worker 退出 | 是       |
| cancelled | 取消或管理器关闭导致停止           | 是       |

典型转换为 queued → running → succeeded。queued 和 running 均可能进入 cancelled；步骤异常、输出校验异常或非零退出可进入 failed。

`submit` 没有实现资源排队调度器：queued 是受理交接状态，不能据此假设已有按 GPU、优先级或配额调度的队列。

## 步骤进度

状态中的 `steps` 保存每个已开始步骤的名字、开始结束时间与百分比。Task 可以在步骤内部调用 `report_progress(percentage)`：

- 数值必须处于 0–100。
- 同一步骤不能倒退。
- 步骤正常结束时自动记录 100。
- 失败步骤有结束时间，但不一定为 100。

步骤生成器可以按中间状态动态产生后续步骤，因此当前步骤数量不一定是完整总数。不能简单把“已执行步骤 / 当前步骤数”当成可靠的整项任务百分比。

## 生命周期记录发布

受理执行时在 `metadata.json` 创建 queued 记录。Runner 在启动步骤、报告进度和记录子调用时更新同一记录。同步步骤和资源清理完成后，准备 `output_params`、确定退出码，并将终态与输出一起原子发布。

失败和取消的任务也保留相同 metadata，包含错误和子调用快照。准备输出前 `output_params` 为空，非零退出码仍可能保留已构建输出。Studio 研究页面筛选 `state=succeeded`，状态查询则包含所有状态。进度事件先追加，再发布对应 metadata 快照。

## 固定名称重跑

```bash
axonx submit --task demo --task-name trial-01 --x 1 --y 2
# 等上一轮进入终态后，才提交同名实验
axonx submit --task demo --task-name trial-01 --x 2 --y 3
```

固定名称对应同一 Task ID。已结束的任务可以被新执行替换，当次执行产物会清理，`persistent/` 保留；活跃任务不能覆盖。

同名重跑清理当次执行文件（包括 metadata.json 和 events.jsonl），但保留约定的 `persistent/` 目录。通过 `self.persistent_dir` 保存累计业务数据；插件负责其格式、更新和并发控制。Run ID 和生命周期记录仍只描述当前执行。显式删除 Task 会一并删除持久数据；展示同步以所选产物原子替换目标 Task 目录。`persistent/` 必须是普通目录，不能是符号链接。

不同参数的实验比较应使用不同名称，例如 `trial-01`、`trial-02`，或使用默认生成名称。同名重跑并不在一个目录中保存完整历史；历史恢复需要事先备份。

## 等待与取消

`wait_task` 要求 `task_id` 和 `run_id`，防止目录已重跑时读到另一轮结果。`stream_task` 按 Task ID 持续跟踪状态与日志，适合实时观察；需要确认某一轮身份时仍应保留 handle。

```bash
axonx status --task-id 'base#demo#trial-01'
axonx cancel --task-id 'base#demo#trial-01'
axonx cancel --run-id '<run_id>'
```

取消操作接受任意一个 ID：`task_id` 取消在 manager 锁内选定的当前执行；`run_id` 精确取消提交结果或状态中的那次执行，不会取消同名的新 Run。同时指定两个 ID 时会校验当前 Task/Run 是否匹配，不匹配则返回 false；未知 ID 也返回 false。若选定 manager 不管理该活跃 Run，则因无法确认终止而报错。任务很快完成时，取消可能返回 false；这是竞态下的正常情况。关闭服务也会停止其管理的 worker，并将受影响运行记为 cancelled。

文件记录可以恢复查询信息，不能自动恢复一个已中断 Python 进程的内存状态。

[复合 Task](../guides/composite-tasks.md) 在父 worker 中同步执行子 Task。子 Task 继承父任务实例名称，重复调用同一注册名会复用 Task ID 并覆盖终态产物，每次调用则有新的 run ID。取消父 Task 来停止该 worker，管理器会将其活动子 Task 收敛为 cancelled；worker 异常退出时则收敛为 failed。即使父 Task 失败，成功子 Task 仍保留自身 metadata，直到后续调用将其覆盖。允许子任务失败后继续也会使父 Task 最终失败，后续尝试成功不会清除早先的失败调用记录。

## 相关文档

[任务管理](../guides/task-management.md) · [工作区](workspace.md) · [日志与恢复](../guides/operations.md) · [Task 契约](../reference/task-contracts.md)

源码：[身份规则](../../../axonx/task/core/identity.py)、[TaskRunner](../../../axonx/task/runtime/runner.py)、[TaskManager](../../../axonx/components/task_manager/local/manager.py)。
