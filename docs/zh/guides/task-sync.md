# 任务快照同步

任务同步把源服务的终态 Task 目录快照复制到目标服务，并传播已确认任务的删除。它适合把完成的研究记录汇总到另一工作区。默认配置关闭同步组件、flush Job 和定时调度，需要同时启用。

![Task 快照同步](../../figures/guides/task-sync.svg)

## 同步范围与方向

同步方向由源端组件的 target 决定。发送方从 Repository 合并变化，只发送具有终态 status 的 Task。queued/running 任务回到待处理队列，结束后再传输。

包括任务目录中的 status、metadata、events 和产物；不包含整个工作区的 Tushare 原始数据、Agent 会话、外部文本日志或插件环境。不迁移 worker，不会让目标继续运行源端进程。

目标同名终态目录将被新快照替换。双方独立实验最好使用不同名称；同步不是保留多个版本的备份机制。

## 准备目标服务

目标使用默认配置中的 sync_tasks 和文件上传能力。配置独立 token 并启动：

```bash
export AXONX_SERVICE_TOKEN='<接收端 token>'
axonx start --service.host 0.0.0.0 --service.port 1024
```

确保源端能访问接收端。目标无需为了接收而启用发送端 sync 组件。收到记录后可以查看结果，但重跑仍需要对应插件、数据与环境。

## 源端最小配置

创建 `sync-source.yaml`，域名为占位示例：

```yaml
extends: default
targets:
  - address: http://archive.example:1024
    token: ${AXONX_SYNC_REMOTE_TOKEN}
components:
  sync:
    default:
      backend: local
      task_repository: default
      target: http://archive.example:1024
      sync_on_start: true
      task_ids: []
      task_id_prefixes: []
      max_archives_per_flush: 4
      max_file_bytes: 104857600
      max_archive_bytes: 268435456
      timeout_seconds: 300
jobs:
  sync_flush:
    enable_serve: false
    steps:
      - backend: sync_flush_step
        sync: default
schedules:
  workspace_sync:
    backend: cron
    job: sync_flush
    cron: "* * * * *"
    concurrency_policy: forbid
```

```bash
export AXONX_SERVICE_TOKEN='<源端 token>'
export AXONX_SYNC_REMOTE_TOKEN='<接收端 token>'
axonx start --config sync-source.yaml
```

sync.target 必须与已配置 targets 地址匹配，否则启动失败。`sync_flush` 在这个示例中不对外公开，由 Scheduler 内部调用；因此不能直接假设 CLI 可以调用它。

## 首次验证

1. 在源端提交并等待一个独立名称 demo 完成。
2. 等待下一个 flush 调度；检查源端日志中错误与同步结果。
3. 在目标查询相同 Task ID 的 status 与 metadata。
4. 若同步研究任务，核对 artifact 文件大小和 sha256。
5. 重启源端时，sync_on_start=true 会重新排队当前记录；这不是仅复制新增文件。

默认有分钟级调度和 Repository 的变更合并延迟，因此它不是实时逐字节复制。

## 过滤与预算

| 选项 | 含义 |
| --- | --- |
| task_ids | 精确 Task ID 白名单 |
| task_id_prefixes | 按 Task ID 前缀匹配 |
| 两组过滤都为空 | 不按身份过滤 |
| 两组都有值 | 精确匹配或前缀匹配即可 |
| max_file_bytes | 单个文件的预算，默认 100 MiB |
| max_archive_bytes | 单个上传归档预算，默认 256 MiB |
| max_archives_per_flush | 每次归档数，默认 4 |
| timeout_seconds | 目标 HTTP 调用超时，默认 300 秒 |

max_archive_bytes 必须大于 max_file_bytes，并应不超过目标上传能力。默认 `/files` 最大上传 256 MiB。文件太大时不应单纯提高源端值而忽略接收端限制。

结果区分 uploaded、deleted、rejected、oversized、deferred 与 archives。deferred 表示本轮归档预算用完，后续继续；oversized 表示任务无法在当前预算内复制，需缩小产物或调整预算；rejected 标明不满足完整快照约束的文件，应检查源端目录。

## 删除、失败与回滚

源端维护已确认任务集合。已确认任务在源端消失且符合过滤时，删除会发送到目标。未成功确认的源端任务不应被当成已同步任务传播删除。

发送端上传归档后调用 sync_tasks，检查 JobResponse.success；HTTP 200 不能替代业务结果。失败的变更重新排队，下轮重试，上传暂存文件会在结束时尝试清理。

接收端校验归档和任务目录，应用替换与删除时保留回滚能力。目标活跃任务不能被同步覆盖；失败应先查接收错误，而不是强制删除正在运行的目录。

回滚处理当前应用过程，不能作为长期历史恢复。意外传播的合法删除或覆盖仍需要独立备份恢复。

## 排障

| 现象 | 检查 |
| --- | --- |
| 一直无传输 | sync、sync_flush、schedule 是否都启用 |
| 启动失败 | target 是否存在于 targets，组件依赖与配置合法性 |
| running 任务不出现 | 发送方仅复制终态，这是正常过滤 |
| 401/502 | 目标 token、连通性和接收日志 |
| 产物过大 | rejected/oversized、文件与归档预算 |
| 目标没有原始数据 | 原始数据本来不属于 Task 快照 |

[调度](scheduling.md) · [远程机器](remote-machines.md) · [备份恢复](operations.md) · [同步 API](../api/plugins-sync.md)

源码：[发送端组件](../../../axonx/components/sync/local.py)、[同步协议实现](../../../axonx/task/sync/)、[默认配置](../../../axonx/config/default.yaml)。
