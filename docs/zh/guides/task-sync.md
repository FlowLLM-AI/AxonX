# 单向任务展示同步

源端将选中新建或变化的任务组推送到独立远程展示工作区，不检查远端状态、不拉取修改、不传播源端删除，也不删除筛选规则移除的目录。同路径目标目录完整替换，清单外的远端目录保留。

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
      model_names: ["experiment-*"]
      rules:
        research: terminal
        online: live
        compare: terminal
      max_archives_per_flush: 4
      timeout_seconds: 300
jobs:
  publish_display:
    backend: scheduled
    expression: "* * * * *"
    enable_serve: false
    steps:
      - backend: sync_flush_step
        sync: default
```

内部 Job 使用 App 时区每分钟运行一次，复用 pipeline 的 Steps、参数校验与取消生命周期。定时调用串行执行，不补跑错过的时刻；设置 `enable_serve: true` 可额外开放手动 HTTP/MCP 调用。停止服务会取消定时 Job，研究 Task 进程仍遵循现有 Daemon 归属。

## 源端筛选与变化检测

`rules` 将工作流注册名映射到 `terminal` 或 `live`。终态发布等待父任务和所选后代结束，实时发布捕获当前证据。`model_names` 使用通配模式，空列表包含全部模型；空规则不选择任务。

每次调用扫描源端元数据，通过执行身份、文件清单、大小、纳秒修改时间和发布策略判断变化，不读取大文件计算内容哈希。发送成功的版本保存在发送端内存中，未变化的组跳过，失败下次重试；源服务重启后重新发布一次。远端删除或修改不会触发重传。内容变化但大小和修改时间均未变化时不会被发现。

模型筛选复用模型 `task_name`、子调用逻辑 `node_name` 和进度 `name`/`group`。选中视图保留执行身份匹配且仍可用的子任务和共享后代，父参数、结果和进度仅保留选中模型；混合父日志和聚合产物省略。子任务被新执行替换后从旧父视图中排除，不关联到旧调用。源端文件不变。

## 传输与展示

发送端生成完整且受预算限制的展示目录，通过 `POST /upload?mode=replace` 上传。工作流组及所选后代按大小拆分为多个归档，后代先发送，根任务最后发送。`max_archives_per_flush` 限制每次调用的归档数，后续调用继续未完成的任务组，并轮转处理其他根任务。任务组完成前保留已成功上传的 Task 版本，重试不重复发送已完成的批次。每个指定目录原子替换，多个归档组成的任务组不保证整体原子性。接收端只校验和替换文件，已有 `task_index` 在下次扫描时发现支持的元数据，默认间隔五秒。文件接收不需要目标端同步组件、回执、专用 Job 或任务元数据解析器。

`transfer_budget_bytes` 默认 512 MiB。每个 Task 独立享有这份展示预算（含预留归档开销），不按 Task 数量平分；每次上传的大小与展开后的归档大小也分别受同一上限限制。源端预算应不高于接收端。过大的日期键 Parquet 可采样为共同的完整交易日后缀，其他文件可明确省略；失败和遗漏会报告。展示元数据保留源身份、源和策略版本、文件覆盖及选中的工作流快照。展示副本不能执行、不能作为研究输入，也不能继续作为发送源。

每个任务组完成后清理源端 `tmp/sync/`；接收端 `tmp/files/` 在成功或回滚完成后清理，回滚失败时保留原目录供恢复。此功能是文件替换，不代替备份或迁移进程、环境。应使用独立展示工作区，因为提供的路径会覆盖同路径目录。
