# 任务快照同步

任务同步把源服务的完整终态 Task 目录复制到目标。每次源服务启动，先读取目标的 `task_sync_index`，再扫描本地终态目录，将缺失或内容不同的快照加入队列。不持久化确认状态或失败记录。

## 范围与生命周期

`task_names` 精确匹配 `<task type>#<registration>#<task name>` 的最后一段，不限制任务类型和注册名。空列表包含所有名称。启动对账使用文件名和内容的 SHA256 摘要，包含 metadata、events 和产物；因此同名任务重跑、同一运行的产物更新都能被识别。计算摘要需要读取两端匹配的快照，大工作区的启动对账耗时更长。

运行期间，Repository 变化按 Task ID 合并，只有终态快照会发送。queued/running 任务跳过，等待后续完成事件。Watcher 故障恢复时重新对账，补齐漏掉的变化。本地删除不会删除远端记录。

快照不包含整个工作区的 Tushare 原始数据、Agent 会话、外部日志和插件环境，不迁移 worker，也不自动复制其他名称的依赖任务。远端重跑仍需要对应插件、数据和执行环境。

## 目标配置

两端都需要更新后的 AxonX 默认配置，包含 `task_sync_index`、`sync_tasks` 和 `/files`。旧接收端没有索引 Job，无法参与启动对账。接收端无需启用发送组件。

```bash
export AXONX_SERVICE_TOKEN='<接收端 token>'
axonx start --service.host 0.0.0.0 --service.port 1024
```

## 源端配置

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
      task_names: [research-model]
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
    job: sync_flush
    cron: "* * * * *"
    concurrency_policy: forbid
```

```bash
export AXONX_SYNC_REMOTE_TOKEN='<接收端 token>'
axonx start --config sync-source.yaml
```

组件的 target 必须匹配配置的目标地址。多个目标分别配置同步组件和独立调度的 flush Job；发往同一目标的名称可以共用组件和归档批次。

`task_ids`、`task_id_prefixes`、`sync_on_start` 已移除，使用时会报错。过滤改用 `task_names`，启动对账始终执行。旧工作区 `sync/*.json` 状态文件不再读取，可以手动清理。

## 批次、失败与预算

多个完整 Task 合并成归档，同一轮 flush 复用 HTTP 连接。默认单文件上限 100 MiB、归档预算 256 MiB、每轮最多四个归档。一个 Task 必须装进一个归档，不拆分大任务。`max_archive_bytes` 必须大于 `max_file_bytes`，并遵守接收端 256 MiB 上传限制。

`SyncReport` 包含 `uploaded`、`rejected`、`oversized`、`deferred`、`archives`。`archives` 表示尝试的归档数。deferred 是尚未尝试的任务，留在内存队列中等待下一轮调度。过大或不完整的快照记录日志后丢弃。

每个批次只尝试一次，失败记录日志后丢弃，其他批次可以继续。发送端校验 `JobResponse.success` 和上传 SHA256，HTTP 200 不代表应用成功。成功或失败后都会尝试清理上传暂存文件。不保存失败列表，也不自动重试。修复连接或大小限制后重启源端，重新对账补齐缺失或旧快照。本地新变化也可以再次触发该任务发送。

启动对账失败时，源端记录日志后继续运行，不进行全量重传。后续本地变化仍可发送；目标恢复后重启源端补齐已有缺口。

接收端拒绝覆盖或删除活跃 Task，应用失败时回滚本次操作。同 ID 终态目录整体替换，不保留历史版本备份。

## 验证

1. 提交名称匹配的 Task，等待终态及下一轮 flush。
2. 对比目标 metadata 和产物 SHA256。
3. 重启源端，完全相同的快照不应进入队列。
4. 同名重跑或更新产物，启动对账应识别新快照。
5. 传输失败时检查日志，修复后重启补齐。

手动同步仍可先 `POST /files` 上传完整 Task 归档，再用 `answer.path` 调用 `sync_tasks`。手动 API 保留显式删除能力；自动发送端不发送删除。

[调度](scheduling.md) · [远程机器](remote-machines.md) · [同步 API](../api/plugins-sync.md)
