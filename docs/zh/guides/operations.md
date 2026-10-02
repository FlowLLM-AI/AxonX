# 日志排障与备份恢复

排障时先确认执行机器、Task ID 和 run_id，再区分协议连接、worker 执行与研究展示。备份恢复应同时考虑文件、插件环境与外部凭据；恢复历史记录不等于恢复已中断进程。

## 建立基本状态

```bash
axonx version
axonx machine_status
axonx list_plugins
axonx list_task_statuses
```

记录服务和插件版本。远程任务的命令应带原目标地址；从本机读到相同 Task ID 也不证明正在查看同一台机器。

带 token 查询 `/health` 可检查协议连通性。缺少 token 时的 401 不表示 worker 故障，见[鉴权指南](authentication.md)。

## 日志来源

| 来源                     | 用于判断                                  |
| ------------------------ | ----------------------------------------- |
| 服务控制台与 log_dir     | 启动、配置、转发、watcher、调度与组件异常 |
| status.error / exit_code | 某轮 Task 最终错误                        |
| read_task_log            | worker 中步骤、插件与模型库的详细日志     |
| events.jsonl             | 进度事件回放，不等于文本日志              |
| metadata.json            | 成功配置和输出，不包含失败堆栈            |

```bash
axonx status --task-id '<Task ID>'
axonx read_task_log --task-id '<Task ID>' --offset -1 --limit 65536
```

日志窗口使用字节偏移。先读尾部找到异常，再根据需要扩大或指定窗口。若 status.log_path 指向外部日志目录，迁移工作区后可能需要同时恢复日志。

## 提交成功但 Task 失败

1. 核对 handle 中的 run_id，排除固定名称重跑。
2. 查看最终 state、error、exit_code。
3. 查看最后失败步骤及 Task 日志。
4. 检查插件输入、上游文件、外部数据权限与模型依赖。
5. 使用新 task_name 重跑，保留失败记录用于对照。

`submit.success=true` 只表示受理成功。`wait_task` 的 success 对应最终 succeeded；不应仅根据 HTTP 200 判断研究成功。

## worker 异常与状态对账

正常 worker 自己写状态。进程异常退出时，TaskManager 的 supervisor/reaper 依据已管理进程和 Repository 记录核对活跃运行，补写错误终态；周期由 reaper_interval_seconds 控制。

如果长时间显示 running，先确认进程是否仍在运行、当前服务是否管理这轮运行、日志是否持续增长，以及磁盘是否可写。不要只根据文件中的 pid 跨机器判断进程生死。

强制 kill 或断电后记录可能没有完整结束信息。先保留文件并检查服务日志，确认数据一致后再以新身份重跑；不建议手工把 state 改成 succeeded。

## 文件存在但页面未更新

Repository 默认监听并轮询记录变化，debounce 等参数使短时间延迟正常。检查 JSON 合法性、task_id/type 与目录是否一致，以及服务是否使用预期工作区。

watcher 出现监视窗口缺失时，Repository/同步会重新检查记录。索引可由有效 status 和 metadata 重建，但不会修复损坏 JSON 或缺失产物。

研究页面使用含 metadata 的目录。失败任务、base demo 或 metadata 缺失任务不保证出现在研究结果页；metadata 有效也不保证所有图表字段齐全。

## 备份清单

| 内容                   | 为什么需要                                 |
| ---------------------- | ------------------------------------------ |
| 完整工作区             | Task 记录、研究产物、原始数据与 Agent 状态 |
| log_dir                | 独立于任务目录的执行日志                   |
| 服务配置与环境变量清单 | targets、路径、调度和连接参数              |
| 插件源码/wheel 与版本  | 重跑时还原相同算法                         |
| Python 与模型依赖信息  | 还原数据格式、设备库和模型加载条件         |
| 外部凭据               | 按独立安全方式保存，不能靠文档示例恢复     |

Linux/macOS 下可在停止写入后使用自己的备份工具。例如工作区和日志在当前目录时：

```bash
# 确认服务与 exec 进程都已停止写入后执行
mkdir -p ./backup
cp -a ./.axonx ./backup/workspace
cp -a ./logs ./backup/logs
```

重复执行前选择新的备份目的目录，避免产生嵌套路径或覆盖未知备份。大数据应采用快照或增量备份工具，命令只是文件复制示例。

## 恢复顺序

1. 停止接收新的任务与文件写入。
2. 在目标位置恢复工作区、日志和配置，核对权限与绝对路径。
3. 安装匹配 AxonX、插件和模型依赖。
4. 启动服务，让 Repository 重新扫描有效记录。
5. 对照备份检查任务数量、metadata、artifact size/sha256。
6. 用独立名称运行 demo，再小范围验证研究插件。

旧 status 的 pid 和 log_path 是当时环境信息，不代表目标机有对应活跃进程。恢复文件后不会自动恢复正在训练的内存状态。

## 同步与备份的区别

任务同步以终态目录为单位，可能替换目标同名目录并传播删除。它不保留任意时点的完整历史，也不包含工作区原始数据、Agent 会话、外部日志和插件环境。

需要可撤销恢复时，应单独保存版本化备份。具体同步预算、回滚和重试见[任务同步](task-sync.md)。

[部署](deployment.md) · [工作区](../concepts/workspace.md) · [任务生命周期](../concepts/task-lifecycle.md)

源码：[管理器](../../../axonx/components/task_manager/local/manager.py)、[worker supervisor](../../../axonx/components/task_manager/local/supervisor.py)、[记录读取](../../../axonx/task/storage/workspace.py)。
