# Job 与 Task

Job 暴露应用能力，Task 同步执行研究并持久化证据。CLI、HTTP、MCP 和 Studio 访问相同的已配置 Job，原生 Task 执行是独立的 CLI 操作。

![Job、命令与 Task 结果](../../figures/concepts/jobs-tasks.svg)

## 对照

| 概念       | 执行方式           | 所有权与输出                                  |
| ---------- | ------------------ | --------------------------------------------- |
| Job        | 异步 Step          | Application，返回 `JobResponse` 和可选事件    |
| Task       | 同步步骤及子任务   | CLI 执行进程，保存 metadata、文件并返回退出码 |
| Task index | 读取工作区记录     | Application，提供摘要、关系图和事件流         |
| Daemon     | 监督服务和定时命令 | 宿主，负责进程生命周期和更新                  |

## 从名称到执行身份

`demo` 等注册名解析到类，`task_name` 标识实例，Task ID 组合类型、注册和实例，例如 `base#demo#check`。`started_at` 区分同一目录的历次执行，机器/PID/进程启动时间标识执行进程。

## 执行结果

`axonx exec --task demo --task-name check --x 1 --y 2` 等待完成，输出业务结果并返回进程退出码。用 `status --detail full` 查看 metadata。同名重跑替换输出并保留 `persistent/`，独立实验记录需使用不同名称。

## 本地与远程执行

本地 `exec` 在 CLI 进程执行。`exec --target HOST:PORT` 调用目标服务的 `cli` Job，由它拥有命令子进程并传输 stdout/stderr 直到完成。HTTP/MCP 调用方可用 `argv: ["exec", "--task", "demo", ...]` 调用 `cli`。命令响应包含 stdout、stderr、exit_code 和截断标志。连接取消可能停止其拥有的命令，重试前先检查证据。

## 选择抽象

研究使用 `BaseTask`，同步子任务调用使用 `run_task()`；异步应用能力使用 Job Step，可复用受管理资源使用 Component。插件只注册 Task，框架 provider 在应用装配时显式提供。

[生命周期](task-lifecycle.md) · [任务管理](../guides/task-management.md) · [架构](architecture.md)
