# 结果展示同步

任务同步发布终态任务的**结果展示副本**，不是可执行的工作区备份。`task_names` 匹配 `<task type>#<registration>#<task name>` 的最后一段；空列表包含所有名称。复合任务和子任务独立应用同一筛选规则。

## 内容与语义

副本包含 `metadata.json`、执行事件、发布的产物及模型或在线清单引用的必要文件。排除上游 `inputs/`、固定模型输入 `model_snapshot/`、未发布文件、临时工作区、外部日志及插件环境。本地硬链接输入快照保持完整。

源指标与研究协议保留原始运行语义。`metadata.replica` 保存 `purpose: display`、源与策略摘要、实际文件大小和 SHA256、省略路径及原因、采样行数与日期范围、源日志路径。目标本地 `log_path` 为空。Studio 标记副本，文件覆盖范围和省略项按需展开。计算消费者拒绝将副本作为研究输入；副本不会作为同步源继续转发。

## 唯一预算

应用级 `transfer_budget_bytes` 默认 536870912（512 MiB），控制每个归档的压缩前总大小，包括 metadata 与 tar 开销，同时控制上传上限。发送端通过 `task_sync_index` 使用两端较小预算。没有独立单文件大小选项；`max_file_bytes`、`max_archive_bytes` 会被拒绝。

能放入预算时保持文件完整。否则按共同的最近完整 `trade_date` 范围重新生成日期型业务 Parquet。采样检查实际编码大小，保留类型及文件元数据，绝不截断字节或单个交易日。模型、JSON、任务记录、报告汇总、交易流水和参考交易日历不采样。最近一个完整交易日仍放不下时省略可采样数据并记录原因；必要的不可采样内容超限则明确拒绝。源文件和原始指标均不改变。

## 配置

两端使用相同应用预算，接收端无需配置同步组件。目标 token 应与接收服务的鉴权 token 一致。

```yaml
extends: default
transfer_budget_bytes: 536870912
targets:
  - address: http://archive.example:1024
    token: ${AXONX_SYNC_REMOTE_TOKEN}
components:
  sync:
    default:
      backend: local
      target: http://archive.example:1024
      task_names: [research-model]
      max_archives_per_flush: 4
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

## 对账、重试与清理

`task_sync_index` 返回 `transfer_budget_bytes` 与 `tasks` 映射，其中每个已校验副本包含 `source_digest`、`policy_digest`。启动时比较源端发布内容和采样策略。相同副本跳过；重跑、产物或预算变化会触发替换。仅被排除的输入内容变化无需重传。

Repository 事件将终态源任务加入队列；Watcher 漏事件恢复后触发对账。启动索引失败在后续 flush 重试。暂时性的准备、上传或提交失败保留队列；确定性无效产物或不可采样内容超限明确报告，避免每分钟无效重试。未尝试批次保留队列。队列仅存于内存，重启对账恢复中断传输。本地删除不自动传播。

一个任务副本完整装入一个归档。接收端验证精确文件清单、大小和哈希，拒绝覆盖活跃任务，并原子提交，失败回滚。成功、失败和取消均清理源端采样临时文件及远端上传暂存文件；取消等待后台准备结束后再清理文件。

## 破坏式格式

两端必须使用新的展示副本格式。旧完整目录归档及旧索引响应直接拒绝，无兼容读取或迁移路径。回测先按统一的 `signals.parquet` 格式重新生成产物，再发布。手动 `sync_tasks` 接受准备好的副本归档或显式删除，不接受未标记的普通任务目录。

## 验证

检查匹配的父子任务均出现、输入快照不存在、样本保留最近完整日期、源文件不变、实际哈希匹配副本清单、重启不重复传输、预算与运行变化可更新、暂时性失败可恢复、临时文件已清理。

[调度](scheduling.md) · [远程机器](remote-machines.md) · [同步 API](../api/plugins-sync.md)
