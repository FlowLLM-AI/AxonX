# Task 生命周期

`axonx exec` 在当前进程中发现并执行已安装的 Task。App 读取工作区数据，提供查询、订阅和展示；Task 定义通过独立 CLI 子进程查询，App 不导入研究插件。

```text
exec → 校验与目录事务 → running → succeeded / failed
```

首份 metadata 就是 `running`，同时写入 `task_id`、`run_id`、`machine_id`、正整数 `pid`、带时区的 `process_started_at`、创建和开始时间。`queued` 已删除。进程启动时间用于识别 PID 复用，不能用 Task 开始时间替代。

## 观察与修正

App 启动扫描和每次轮询都会检查本机原始 `running` 记录，包括文件属性未变的记录。进程仍匹配则保持原样；确认进程退出或 PID 被复用时，将该 Run 和未完成步骤、子调用记录修正为 `failed`，退出码为框架错误码 `1`，原因注明检测时间。`finished_at` 为发现中断的时间，不推测真实退出时刻或信号。

外机记录、展示副本、进程访问权限不足时不回写。进程存在只证明执行进程仍存在，不证明计算没有卡住。服务重启不会终止独立 exec，也不会自动重试或补放 cron。

## 重跑与终止

固定 Task ID 的终态 Run 可以重跑，打印 `Overwrite`，清理旧 Run 文件但保留 `persistent/`。本机残留 `running` 会先校验并修正；仍存活或无法确认的运行会拒绝覆盖并打印精确的 kill 命令。外机运行需在原机器操作，`machine_id` 不能推导服务地址。损坏记录、符号链接和展示副本不会被盲目覆盖。

```bash
axonx kill --task-id '<Task ID>' --run-id '<Run ID>'
axonx kill --task-id '<Task ID>' --run-id '<Run ID>' --target '<host:port>'
# 明确需要强制终止时
axonx kill --task-id '<Task ID>' --run-id '<Run ID>' --force true
```

kill 必须匹配本机原始 Run、PID 和进程启动时间。默认发送 SIGTERM 并等待，`--timeout` 默认 5 秒；超时不会自动升级信号。`--force true` 显式使用 SIGKILL。复合 Task 的子任务共享进程，终止会影响整个执行进程及其子进程；可识别父 Run 时使用根执行记录。退出后统一修正同一进程的未完成记录。

创建新 Run 与观察修正使用工作区 `.task-records/` 中的短事务锁，检查、清理和首份状态发布属于一个事务。运行期间不持有此锁。此目录由框架保留，工作区浏览器隐藏它并拒绝删除。不要手动改写活动记录或并发清空工作区。

旧内部路径、缺少进程身份的 metadata、旧 queued 状态均不提供兼容读取或自动迁移；保留需要的产物后重新执行。`wait_task` 始终核对 Task ID 和 Run ID。
