# Task 执行与观察

在已安装插件并准备好数据的机器上，通过 CLI 执行 Task。本地执行不需要 HTTP 服务：

```bash
axonx exec --task demo --task-name add-01 --x 1 --y 2
```

命令在前台执行，输出 Task 结果，并返回 Task 的退出码。后台运行交给终端或进程管理工具。每个 Task 自行将参数、进度、输出和生命周期写入 `<workspace>/<task_type>/<task_id>/metadata.json`；示例的 Task ID 为 `base#demo#add-01`。

观察服务应与执行进程使用相同的 workspace 和日志目录。服务轮询 metadata，提供 Task 只读查询。服务不重新启动或取消独立 Task；启动与轮询只修正已确认死亡的本机原始 Run，存活、外机、副本和权限未知记录保持原状态。

## 查看定义

```bash
axonx exec
axonx list_installed_task_definitions
axonx get_task_definition --task demo
```

不带参数的 `exec` 列出本地已安装 Task。两个定义查询 Job 读取所选服务的安装环境。Studio 的任务定义页面展示说明和输入输出 Schema，不再提供启动表单。

## 查询状态与日志

```bash
axonx list_task_ids
axonx list_task_statuses
axonx status --task-id 'base#demo#add-01' --detail full
axonx read_task_log --task-id 'base#demo#add-01' --offset -1 --limit 8192
axonx get_task_graph --task-id 'base#demo#add-01'
```

Run ID 位于 metadata 和状态响应中。查询特定执行的日志时传入 `--run-id`。日志偏移以字节计，后续读取使用响应返回的偏移。Studio 按 Task 类型和注册名分组，保留搜索、状态和类型筛选，以及每组 50 条的分页；列表和详情不再提供取消或删除操作。

## 等待与跟踪

```bash
axonx wait_task --task-id 'base#demo#add-01' --run-id '<metadata 中的 run_id>' --client-timeout 600
axonx stream_task --task-id 'base#demo#add-01' --stream true --client-timeout 600
```

等待操作检查准确的 Run ID，并返回终态结果。断开观察请求不会停止本地启动的 Task。同名任务被替换后，绑定旧 Run 的查询会失败。

## 失败与重跑

Runner 会记录能够进入 Python 清理流程的失败。进程被强制终止时，metadata 可能停留在 running；启动/轮询及下一次 exec 会将确认已死亡的本机原始 Run 修正为 failed。进程终止使用显式 `axonx kill`，详见 [Task 生命周期](../concepts/task-lifecycle.md)。

固定任务名会复用 Task ID，替换终态输出并保留 Task 自有的 persistent 数据。保留独立实验记录时使用新名称。同名执行、删除和同步需由外部协调；metadata 原子替换不代表这些操作已经串行化。

[组合任务](composite-tasks.md)在父任务进程中同步执行子任务。子任务保留独立身份和 metadata，但共享执行进程。框架执行成功与研究效果需要分别验证。

[Task API](../api/tasks.md) · [生命周期](../concepts/task-lifecycle.md)
