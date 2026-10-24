# Task 生命周期

`axonx exec` 解析并校验已安装的 Task，通过 `TaskCommandExecutor` 和 `TaskRunner` 在当前进程执行。服务不再创建排队记录，也不启动 Task worker。

```text
exec → 校验 → queued → running → succeeded / failed
                     ↘ metadata、事件、日志、产物
服务 → TaskRepository → 读取快照 → API / Studio
```

Runner 创建 Task 和 Run 身份、原子发布 metadata、执行同步步骤并关闭资源。组合任务的子任务在相同进程运行，同时发布各自的记录。metadata 包括输入、输出、步骤、子任务、进程身份与产物引用。

固定名称可替换终态记录并保留 persistent 数据；自动名称创建独立 Task。同名任务的并发操作需由外部协调。

服务只观察最后发布的生命周期快照，不根据持久化 PID 获取进程控制权，不将中断任务自动标记为失败，也不在重启时终止 Task。进程被强制终止可能留下过期的 running 记录。进程控制和显式恢复由观察服务之外的执行环境负责。

`wait_task` 检查准确的 Task/Run 对；日志、流、关系图和状态查询均不拥有或控制执行。专用提交、取消和删除 Task 的 Job，以及服务到 worker 的交接协议已经删除，不保留兼容别名。Task 来源为 `exec` 或 `unknown`。
