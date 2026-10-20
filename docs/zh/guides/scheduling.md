# 定时 Job 调度

Scheduler 按 Cron 和时区触发配置中的 Job，传入固定 arguments。默认 `schedules` 为空，没有后台定时研究。调度并发策略限制的是被调用 Job 的生命周期，提交后继续运行的 Task 需要单独控制。

定时 Task 使用 `job: submit`，在 `arguments.task` 中指定注册名；固定 Task 参数放入 `arguments`，无需专用提交 Job。

![Cron 与后台 Task 的边界](../../figures/guides/scheduling.svg)

## 最小配置

下面每小时调用一次版本 Job，适合检查调度配置且不产生外部副作用：

```yaml
extends: default
schedules:
  hourly_version:
    backend: cron
    description: 每小时检查服务版本。
    job: version
    cron: "0 * * * *"
    timezone: Asia/Shanghai
    arguments: {}
    concurrency_policy: forbid
```

```bash
axonx start --config scheduled.yaml
```

将配置保存为 scheduled.yaml 后再运行命令。Scheduler 与服务在同一 Application 内启动，不需要单独部署另一调度进程。

启动时检查 Job 是否存在，并用该 Job 的 Schema 校验 arguments。不合法 Cron、未知时区、未知 Job 或参数错误都会阻止正常启动，不能靠等到触发时再解决。

## Cron 与时区

| 示例           | 意图         |
| -------------- | ------------ |
| `* * * * *`    | 每分钟       |
| `0 * * * *`    | 每小时整点   |
| `0 18 * * 1-5` | 工作日 18 点 |
| `30 2 * * *`   | 每天 2:30    |

默认调度时区使用 Application 的 timezone，默认 Asia/Shanghai；每个 schedule 可覆盖。

实现使用 croniter 计算下一次时间。这不是交易日历，工作日表达式也不能排除节假日或闭市日。数据下载、训练和回测必须自行验证需要的交易日范围。

服务必须运行到触发时刻。当前循环计算下一次执行，没有持久化补跑历史错过触发的队列，也不保证停机期间的调度自动补偿。

## 传入 Job 参数

```yaml
schedules:
  daily_demo:
    backend: cron
    job: submit
    cron: "0 18 * * 1-5"
    arguments:
      task: demo
      x: 1
      y: 2
    concurrency_policy: forbid
```

省略 task_name 每次生成独立 Task ID，可以保留多轮结果。使用固定名称会在终态后替换同名目录，任务仍活跃时下一次提交失败。

`submit` 的外层 Schema 允许透传参数，具体 Task 的字段仍由 input_cls 验证；调度启动通过不代表所有插件运行前置条件都成立。

## 并发策略

| 策略    | 上次 Job 仍在运行时                     |
| ------- | --------------------------------------- |
| forbid  | 跳过新触发并记录日志，默认值            |
| allow   | 同时执行新的 Job                        |
| replace | 取消旧 Job 调用，等待取消，再触发新调用 |

例如 submit 几乎立即返回 TaskHandle，但训练 worker 可以继续数小时。此时 forbid 看见 submit Job 已结束，下次仍会提交新的训练 Task。

replace 取消的是 asyncio Job 调用，不应被解释为取消它先前启动的全部 worker。若要限制研究重叠，可写自定义 Job 查询目标任务状态、保留 run_id 并等待终态，或在提交前显式拒绝重叠研究。

## 调度内部 Job

任务同步常把 sync_flush 设置为 `enable_serve: false`，仅通过内部 Dispatcher 被调度调用：

```yaml
schedules:
  workspace_sync:
    backend: cron
    job: sync_flush
    cron: "* * * * *"
    concurrency_policy: forbid
```

此片段需要先按[任务同步](task-sync.md)配置 sync 组件和 sync_flush Job，不是独立完整配置。调度目标不要求作为公开 HTTP Job 暴露。

## 运行检查与关闭

查看服务日志中的跳过、异常和 Job 失败消息。Scheduler 检查 response.success，业务失败会记 warning；失败不会自动变成另一个补跑任务。

对于 submit 调度，另查 Task 状态与日志确认研究完成。外部通知 Job 还应考虑重复发送与失败重试语义，不能只套用每天 Cron 便视为可靠通知流程。

关闭 Application 时会停止调度循环并取消仍在执行的 Job。TaskManager 的 worker 关闭由自己的生命周期负责，详见[部署](deployment.md)。

[Task 管理](task-management.md) · [任务同步](task-sync.md) · [配置参考](../reference/configuration.md) · [Job 与 Task](../concepts/jobs-and-tasks.md)

源码：[CronScheduler](../../../axonx/components/scheduler/cron.py)、[ScheduleConfig](../../../axonx/config/models.py)。

## 任务中心与执行来源

Studio 任务中心统一按任务标识分组展示所有 Task，不区分定时或手动来源。搜索、状态和类型筛选及分组操作适用于所有 Task。定时配置和 Job 触发历史可在对应的日常运行页面查看。

`list_schedules` 返回调度配置和当前触发状态。`submit` Job 触发成功仅表示 Task 已被接受，不表示 Task 已完成。触发历史会持久化并在重启后恢复，被中断的运行中触发记录会标为取消。

| 参数              | 默认值  | 含义                                          |
| ----------------- | ------- | --------------------------------------------- |
| `name`            | 省略    | 精确匹配调度名称，省略时列出全部配置的调度    |
| `include_history` | `false` | 返回最近触发历史及最近 Job 结果               |
| `history_limit`   | `20`    | 每个调度选取最近 1–200 条记录，按时间正序返回 |

默认响应省略 `history` 和最近触发记录的 `result`。显式查询历史时，`history_total` 给出截取前的保留记录总数；`history_scheduler_ids` 列出当前 Job 在保留历史中的服务标识，Task 归组不依赖触发记录是否落在显示窗口内。存储保留天数与查询数量限制相互独立。

Studio 只查询当前页面的调度，每个调度最多请求 200 条记录，并标明历史未全部显示。窗口外的较早保留触发记录不列出，其 Task 来源归组仍然有效。

Task 元数据和列表摘要包含框架管理的 `source`：`kind` 区分 `submit`、直接 `exec` 和未知来源；可选 `schedule` 包含定时任务名称、Job、触发 ID 和触发时间。Worker 和组合子 Task 保留同一触发归属。来源信息不进入插件输入参数或 Task 身份。用户、API 和 Agent 主动提交均标记为 `submit`，不通过 Task 名称推断调用方。

固定名称 Task 仍仅保留当前 Run。按定时任务分组不会增加历史 Run。展示副本保留生产方来源，但不因此成为本机管理的 Worker。

所选服务拥有的定时来源 Task 正在排队或运行时，禁止**服务更新与重启**，`force=true` 也不能绕过。已结束的 Task、尚未触发的定时配置和其他服务拥有的 Worker 不受此限制。Task 取消、删除和提交保持原有行为。参见[服务自更新](self-update.md)。

```bash
axonx list_schedules --target node-b:1024
axonx list_schedules --name daily --include-history true --history-limit 10 --target node-b:1024
```
