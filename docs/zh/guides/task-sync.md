# 结果展示同步

同步创建有大小限制的展示副本，不是可执行工作区备份。普通 Task 在终态后选择；显式 live_task_ids 选择父任务组及其对应子执行快照。task_names 按 Task ID 最后一段筛选，空列表包含全部名称。

![源工作区证据与独立工作区中的只读展示副本](../../figures/concepts/workspace.svg)

沿虚线复制路径读取右侧展示工作区。研究消费方仍读取经过验证的源产物，副本路径用于查看证据。

## 内容与语义

副本包含 metadata、进度证据和引用的已发布产物，不包含环境、原始工作区、未引用文件或上游输入/模型快照。缺失文件记录在 replica.omitted，源声明和指标保持原样。副本不能执行、不能作为可修改的研究输入，也不继续转发为同步源。

## 统一预算

transfer_budget_bytes（默认 512 MiB）限制上传和含 tar 封装的归档大小，发送/接收使用较小预算。较大的日期键 Parquet 可采样为共同的完整交易日后缀，大小、修订、源行数和覆盖范围区分副本与完整源产物。其他文件可省略，不会悄悄截断。

## 配置

```yaml
extends: default
targets:
  - address: http://display:1024
    token: ${DISPLAY_TOKEN}
components:
  sync:
    default:
      backend: local
      target: http://display:1024
      task_index: default
      task_names: []
      live_task_ids: []
      max_archives_per_flush: 4
      timeout_seconds: 300
jobs:
  sync_flush:
    parameters: { type: object, properties: {}, additionalProperties: false }
    steps:
      - backend: sync_flush_step
        sync: default
```

配置可选 Job 后显式调用 `axonx sync_flush`，默认未启用。Cron 支持本地 Task exec，不能将 Job 调度块直接移入 cron；可由宿主工作流周期调用 flush。同步组件依赖 task_index。

## 协调、重试与清理

索引事件将符合条件的源记录加入待处理队列；flush 协调遗漏事件、生成有限批次、上传归档并通过 sync_tasks 应用。临时失败可在后续 flush 重试，不安全或超预算证据报告错误/省略。检查同步报告，上传清理和目标协调属于同步消费者。

## 连续父任务快照

LiveSnapshot 记录 source_id、root_task_id、root_started_at、captured_at 和有序 revision。子集合跟随父任务实际调用，而非只匹配名称。稳定发布和源未变检查防止混合快照。副本包含文件/策略修订、采样、省略及可选有限日志信息。

## 验证

核对源/目标、执行启动身份、产物覆盖和目标只读标识。同步不恢复进程、不安装插件、不传凭据，也不代替备份。

源码：[同步组件](../../../axonx/app/components/sync/local.py)、[副本构建器](../../../axonx/app/components/sync/replica.py)。
