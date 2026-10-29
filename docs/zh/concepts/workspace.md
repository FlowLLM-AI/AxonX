# 工作区与持久记录

工作区保存任务状态、成功结果与研究产物，是 Studio 和任务查询共同读取的数据来源。默认根目录为启动目录下的 `.axonx`，内置默认配置支持通过 shell 或 `.env` 中的 `AXONX_WORKSPACE_DIR` 指定根目录，也可通过配置项 `workspace_dir` 或 CLI 参数 `--workspace-dir` 显式设置。日志目录独立配置，默认是 `logs`。

![Task 记录、产物读取方与有大小限制的展示副本](../../figures/concepts/workspace.svg)

## 目录布局

下面是包含 demo 和一个研究插件任务的示意布局，插件文件名以实际产物为准：

```text
.axonx/
  base/
    base#demo#trial-01/
      metadata.json
      events.jsonl
  etl/
    etl#my-etl#dataset-01/
      metadata.json
      events.jsonl
      dataset.parquet
  train/
  predict/
  backtest/
  analysis/
  inference/
  tushare/                       # 数据下载任务写入的原始数据
  plugins/artifacts/             # CLI 默认 wheel 构建缓存
  agent/                         # 默认 Agent 配置下的会话相关数据
logs/                            # 独立日志目录，不一定在工作区内
```

目录规则是 `<task_type>/<task_id>`，不是 `<task_type>/<注册名>/<started_at>`。Task 类型目录来自枚举，某个目录存在并不代表对应算法插件已经安装。

保留目录 `persistent/` 用于 Task 的累计业务数据。同名重跑保留它并清理其他运行文件；显式删除 Task 时一并删除，展示同步则以所选发布产物替换目标目录。插件负责其数据格式、更新和加锁，该路径必须是普通目录，不能是符号链接。

## 运行记录

| 文件            | 生命周期             | 内容                                                                                    |
| --------------- | -------------------- | --------------------------------------------------------------------------------------- |
| `metadata.json` | 执行启动至终态       | Task ID、started_at、进程身份、输入输出、状态、步骤、错误、退出码、日志路径和子调用记录 |
| `events.jsonl`  | 执行器报告进度时追加 | 可回放的进度事件，每行一个 JSON 对象                                                    |

一个原子 metadata 快照是权威 Task 记录。`TaskExecutor` 在同步执行进程中更新它，包含子调用、清理和最终输出。运行准备与显式 `kill` 可以收敛已确认退出的本地进程；查询只观察文件。同名重跑会替换 `metadata.json` 和 `events.jsonl`，两者都不保存以往执行的完整历史。

子调用记录保存在 `metadata.json.children`；子目录仍位于各自类型目录下，不嵌套在父目录内。同步或删除父任务不会自动包含子任务。

读取端将损坏、不安全或身份不匹配的记录视为缺失，不读取 FIFO 或跟随符号链接。生命周期操作可以重试临时 I/O 错误。

## 产物的相对路径

研究 Task 的 `output_params.artifacts` 可以记录产物：

```json
{
  "artifacts": {
    "dataset": {
      "path": "data/dataset.parquet",
      "size": 10240,
      "revision": "<size>:<mtime_ns>"
    }
  }
}
```

这里的 path 相对 Task 目录。因此工作区预览路径为：

```text
etl/etl#my-etl#dataset-01/data/dataset.parquet
```

不能把 artifact 的 path 直接当工作区根路径，也不能用绝对路径或 `../` 逃离任务目录。生产插件应在文件写完后记录 size 和 revision。

## 日志在哪里

`status.log_path` 记录具体日志位置。日志系统由 `log_dir` 控制，Task 日志不保证固定存在于任务目录中。通过 `read_task_log` 或 Studio 任务详情读取，而不是猜测 `<task_dir>/log.txt`。

`events.jsonl` 是进度事件日志，不等于 Python 文本日志。备份任务目录能保留进度事件，若文本日志放在外部目录，应单独备份。

## 索引与文件的关系

TaskIndex 周期扫描类型目录下的 metadata（默认每 5 秒），为列表和依赖图维护快照。单任务状态、等待和流式观察直接读取当前 metadata。重启可从有效记录重建查询信息，不会重新训练模型或下载原始数据。

任务列表包含所有有效生命周期记录。Studio 研究页面选择 `state=succeeded` 的记录，metadata 存在不代表实验成功。

## 浏览目录

```bash
axonx list_entries --path ''
axonx list_task_directories --task-type base
axonx preview_file --path 'base/base#demo#check/metadata.json' --max-bytes 8192
```

路径相对于所选服务工作区。list_entries 按 offset 分页并限制列表大小。list_task_directories 选择类型目录中包含 metadata.json 的目录，不限制生命周期状态。Task ID 包含 #，shell 中应加引号。

## 预览记录与产物

使用当前 metadata.output_params.artifacts 的路径，在 Task 目录内解析。preview_file 支持文本、Markdown、JSON/YAML、CSV、JSONL、Parquet，各格式响应字段不同。检查 parse_error、截断、row_count、has_more，不假设所有文件返回相同形态。

## 格式与大小限制

`max_bytes` 控制文本、Markdown、JSON 和 YAML 预览（最多 32 MiB）；`offset` 和 `limit` 控制行格式分页，每页最多 5000 行。JSONL 有独立的 512 KiB 页预算，不受 `max_bytes` 控制。CLI 默认 20 行/8192 字节。JSONL 保留错误/未完整行的原始 content 和 parse_error，正常行包含 data。有限预览不是完整产物，也不能代替研究质量验收。

## 清理文件和目录

delete_entries 接受 JSON paths 数组。这是通用文件能力，不保护活动 Task 进程。删除当前任务目录前停止写入者，检查源身份，并与执行串行协调。删除也移除 persistent/，不会停止进程或重建下游输出。

## 上传与后续消费

POST /upload 或 HttpClient.copy_file 在 tmp 暂存单文件。StagedFile 包含 path、size、绝对 location。目标机插件安装使用 location，同步和清理使用相对 path。上传不安装文件，插件安装不自动删除暂存文件。应在 finally 清理，详见[上传 API](../api/workspace.md)。

一致性备份见[运维与恢复](../guides/operations.md#备份与恢复)；展示副本会省略数据，不能代替备份。

[Task 契约](../reference/task-contracts.md) · [研究产物](../reference/research-artifacts.md) · [工作区 API](../api/workspace.md)
