# Job、Task 与生命周期

Job 暴露应用能力，Task 同步执行研究并持久化证据。CLI、HTTP、MCP 和 Studio 访问相同的已配置 Job，原生 Task 执行是独立的 CLI 操作。

![Job 命令归属、Task 执行与持久化证据](../../figures/concepts/task-execution.svg)

## 对照

| 概念       | 执行方式           | 所有权与输出                                  |
| ---------- | ------------------ | --------------------------------------------- |
| Job        | 异步 Step          | Application，返回 `JobResponse` 和可选事件    |
| Task       | 同步步骤及子任务   | CLI 执行进程，保存 metadata、文件并返回退出码 |
| Task index | 读取工作区记录     | Application，提供摘要、关系图和事件流         |
| Daemon     | 监督服务和定时命令 | 宿主，负责进程生命周期和更新                  |

## 从名称到执行身份

`task_type`、注册名和 `task_name` 组成 `type#registration#instance`。metadata 的 `started_at` 标识当前执行。运行所有权还包括 `machine_id`、`pid`、`process_started_at`、可选的可达 `execution_target` 和源 `workspace_dir`。

`demo` 等注册名解析到类，`task_name` 标识实例，例如 `base#demo#check`。

## 本地与远程执行

本地 `exec` 在 CLI 进程执行。`exec --target HOST:PORT` 调用目标服务的 `cli` Job，由它拥有命令子进程并传输 stdout/stderr 直到完成。HTTP/MCP 调用方可用 `argv: ["exec", "--task", "demo", ...]` 调用 `cli`。命令响应包含 stdout、stderr、exit_code 和截断标志。连接取消可能停止其拥有的命令，重试前先检查证据。

## 选择抽象

研究使用 `BaseTask`，同步子任务调用使用 `run_task()`；异步应用能力使用 Job Step，可复用受管理资源使用 Component。插件只注册 Task，框架 provider 在应用装配时显式提供。

## 状态含义

Task 状态为 `running`、`succeeded`、`failed`。成功结果退出码为 0，进程停止和异常会导致失败。步骤状态还包括 pending、waiting、done、missed、skipped。业务窗口 incomplete 不一定使整个 Task 失败。

## 步骤进度

执行器运行 `build_task_steps()` 生成的同步 callable，记录进度和计时，关闭资源后构建最终输出。`report_progress()` 支持命名子步骤，生命周期完成前应停止后台生产者。`publish_output()` 持久化经校验的部分业务结果。

## 生命周期记录发布

`metadata.json` 是当前生命周期文档，通过原子替换发布完整快照；步骤事件日志支持观察。最终业务输出和终态在同一 metadata 中发布。目录没有协调锁，同名执行和并发变更需要调用方串行化。

## 固定名称重跑

运行时核对旧执行已停止，拒绝展示副本以及未确认或异机的 running 记录，再替换当前文件并保留 `persistent/`。自动名称发生冲突时拒绝执行。显式重跑会推进 `started_at`，目录不是不可变历史。替换生产任务前应消费或固定其产物。

## 等待与停止

`wait_task` 内部捕获当前 `started_at`，等待时改变则失败。查询不修正失效 running 状态。启动检查和显式 `kill` 可修正确认已退出的本机记录；权限不足和异机进程保持未验证。

`axonx kill --task-id ID --timeout 5 --force false` 核对身份，停止后代和根执行并重新读取记录。子任务共享根执行进程。远程停止使用源机器和源工作区，不使用副本观察机的挂载路径。观察或删除不能代替停止进程。

[Task 契约](../reference/task-contracts.md) · [任务管理](../guides/task-management.md)
