# 工作区与持久记录

工作区保存任务状态、成功结果与研究产物，是 Studio 和任务查询共同读取的数据来源。默认根目录为启动目录下的 `.axonx`，内置默认配置支持通过 shell 或 `.env` 中的 `AXONX_WORKSPACE_DIR` 指定根目录，也可通过配置项 `workspace_dir` 或 CLI 参数 `--workspace-dir` 显式设置。日志目录独立配置，默认是 `logs`。

![Task 记录、产物读取方与有大小限制的展示副本](../../figures/concepts/workspace.svg)

## 目录布局

下面是默认配置下的运行数据布局。目录按需创建；`<...>` 表示实际标识，插件产物以具体 Task 为准。

```text
<workspace_dir>/                         # 默认 .axonx/
├── tasks/                               # 固定名字的 Task
│   └── <task_type>/<task_id>/
│       ├── metadata.json                # 当前执行的权威记录
│       ├── events.jsonl                 # 进度事件
│       ├── task.log                     # 启用文件日志时写入
│       ├── persistent/                  # 同名重跑保留的执行历史和累计数据
│       └── ...                          # 插件产物，如模型、报告、比较结果
├── tmp/
│   ├── tasks/<task_type>/<task_id>/      # 自动名字的 Task，内部结构同上
│   ├── uploads/<upload_id>/<file>        # 上传暂存
│   ├── sync/
│   │   ├── send-<operation_id>/          # 同步发送暂存
│   │   └── receive-<operation_id>/       # 同步接收、校验与替换暂存
│   └── plugins/<source_fingerprint>/
│       ├── <plugin>.whl                 # 可重新构建的 wheel 缓存
│       └── .build.lock                  # 并发构建锁
├── tushare/                             # 共享原始数据，独立于采集 Task
│   ├── stock_basic.parquet
│   ├── namechange.parquet
│   ├── trade_cal.parquet
│   └── <YYYY>/<YYYYMMDD>/
│       ├── daily.parquet
│       ├── adj_factor.parquet
│       ├── stk_limit.parquet
│       └── index_weight.parquet
├── daemon/<service_id>/                  # 每个服务的守护进程状态
│   ├── daemon.lock
│   ├── plan.json
│   ├── processes.json
│   ├── service.log                      # 服务进程的控制台输出
│   ├── supervisor.py
│   ├── update.py
│   └── updates/<update_id>/
│       ├── plan.json
│       ├── record.json
│       ├── update.py
│       └── update.log
└── agent/
    ├── claude/<component_name>/          # Claude SDK 配置与运行状态
    └── session-store/<project_key>/<session_id>/
        ├── transcript.jsonl
        ├── summary.json
        └── <subpath>.jsonl               # 可选：子会话记录

<log_dir>/                               # 独立配置，默认 logs/
├── YYYY-MM-DD_HH-MM-SS_<pid>.log          # 服务与启动阶段日志，另有轮转文件
└── cron/entry-<index>.log                 # 定时进程的控制台输出
```

`workspace_dir` 与 `log_dir` 独立解析，`logs/` 不默认位于 `.axonx/` 内。Agent 的状态和会话路径可配置，插件构建的 `--output` 可指定其他输出目录；上图列出默认位置。daemon 的本机通信 socket 位于系统临时目录，不在工作区中。

固定名字使用 `tasks/<task_type>/<task_id>/`。自动命名保留格式为 `YYYYMMDDHH` 加四位字母数字；匹配该格式的名字（包括子任务继承名字）使用 `tmp/tasks/<task_type>/<task_id>/`。Task ID 仍为 `<类型>#<注册名>#<名字>`。新自动命名根任务不会覆盖已有目录；同一父任务的子调用重试可以复用目录。类型枚举为 base/api/etl/analysis/train/predict/portfolio/inference/backtest。

例如固定名训练任务位于 `tasks/train/train#qlib_a158_train#baseline/`，自动命名任务位于 `tmp/tasks/train/train#qlib_a158_train#2026102912aB3d/`。命名判断只依赖最终名字，不增加存储类别字段。参数比较使用普通分析 Task，`summary_stats.csv` 和 `comparison.json` 保存在对应 Task 目录中。

保留目录 `persistent/` 用于 Task 的累计业务数据。同名重跑保留它并清理其他运行文件；显式删除 Task 时一并删除，展示同步则以所选发布产物替换目标目录。框架管理 `persistent/task.lock` 和 `persistent/history.jsonl`，复用 `TaskJournal` 在每次执行结束后追加一行完整终态元信息 JSON；插件管理其他业务文件，不得覆盖该历史，该路径必须是普通目录，不能是符号链接。

## 运行记录

| 文件                       | 生命周期                                  | 内容                                                                                    |
| -------------------------- | ----------------------------------------- | --------------------------------------------------------------------------------------- |
| `metadata.json`            | 执行启动至终态                            | Task ID、started_at、进程身份、输入输出、状态、步骤、错误、退出码、日志路径和子调用记录 |
| `persistent/history.jsonl` | 每次执行结束追加一行 JSON，跨同名重跑保留 | 完整终态执行元信息                                                                      |
| `events.jsonl`             | 执行器报告进度时追加                      | 可回放的进度事件，每行一个 JSON 对象                                                    |

一个原子 metadata 快照是权威 Task 记录。`TaskExecutor` 在同步执行进程中更新它，包含子调用、清理和最终输出。运行准备与显式 `kill` 可以收敛已确认退出的本地进程；查询只观察文件。同名重跑会替换 `metadata.json` 和 `events.jsonl`，两者都不保存以往执行的完整历史。

子调用记录保存在 `metadata.json.children`；子目录仍位于各自类型目录下，不嵌套在父目录内。工作流同步选择仍可用且执行匹配的子任务；删除父任务不自动删除子任务。

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
tasks/etl/etl#my-etl#dataset-01/data/dataset.parquet
```

不能把 artifact 的 path 直接当工作区根路径，也不能用绝对路径或 `../` 逃离任务目录。生产插件应在文件写完后记录 size 和 revision。

## 日志在哪里

启用文件日志时，`status.log_path` 为相对 Task 目录的 `task.log`，记录该 Task 及嵌套子任务日志并排除兄弟任务。通过 `read_task_log` 或 Studio 读取。日志与当前执行同生命周期：允许的同名重跑会替换日志，删除 Task 会一并删除；不受服务日志过期清理影响。

`events.jsonl` 保存进度事件。`log_dir` 单独保存服务及启动阶段日志，排除 Task 范围的消息。定时进程默认关闭控制台日志，避免 cron 输出重复保存 Task 日志；显式 `--log-to-console true` 可以覆盖此默认值。

## 索引与文件的关系

TaskIndex 周期扫描类型目录下的 metadata（默认每 5 秒），为列表和依赖图维护快照。单任务状态、等待和流式观察直接读取当前 metadata。重启可从有效记录重建查询信息，不会重新训练模型或下载原始数据。

任务列表包含所有有效生命周期记录。Studio 研究页面选择 `state=succeeded` 的记录，metadata 存在不代表实验成功。

## 浏览目录

```bash
axonx list_entries --path ''
axonx list_task_directories --path tasks/base
axonx preview_file --path 'tasks/base/base#demo#check/metadata.json' --max-bytes 8192
```

路径相对于所选服务工作区。`tmp/uploads/` 的过期清理仅处理上传，不遍历临时 Task、同步暂存或插件缓存。同步暂存在操作结束时清理；临时 Task 和缓存没有自动过期清理。list_entries 按 offset 分页并限制列表大小。list_task_directories 选择类型目录中包含 metadata.json 的目录，不限制生命周期状态。Task ID 包含 #，shell 中应加引号。

## 预览记录与产物

使用当前 metadata.output_params.artifacts 的路径，在 Task 目录内解析。preview_file 支持文本、Markdown、JSON/YAML、CSV、JSONL、Parquet，各格式响应字段不同。检查 parse_error、截断、row_count、has_more，不假设所有文件返回相同形态。

## 格式与大小限制

`max_bytes` 控制文本、Markdown、JSON 和 YAML 预览（最多 32 MiB）；`offset` 和 `limit` 控制行格式分页，每页最多 5000 行。JSONL 有独立的 512 KiB 页预算，不受 `max_bytes` 控制。CLI 默认 20 行/8192 字节。JSONL 保留错误/未完整行的原始 content 和 parse_error，正常行包含 data。有限预览不是完整产物，也不能代替研究质量验收。

## 清理文件和目录

| 路径           | 用途与清理规则                                                                               |
| -------------- | -------------------------------------------------------------------------------------------- |
| `tushare/`     | 共享原始数据；清理 Task 时保留。采集记录与原始数据分别存储，删除采集 Task 不会删除原始数据。 |
| `tasks/`       | 按名字人工确认后删除；同时检查下游依赖，删除父 Task 不会级联删除子 Task。                    |
| `tmp/tasks/`   | 集中存放临时 Task；执行结束且不再被依赖后可清理，没有自动过期机制。                          |
| `tmp/uploads/` | 上传暂存；默认在后续上传时清理超过 7 天的文件，也可由调用方主动删除。                        |
| `tmp/sync/`    | 操作结束自动清理；异常退出遗留目录需确认同步已停止后删除。                                   |
| `tmp/plugins/` | 可重新构建的缓存；无构建或安装正在使用时可清理，不会卸载 Python 环境中已安装的插件。         |
| `daemon/`      | 服务运行状态和更新记录；运行中的服务仍需要这些文件，停用的服务目录经确认后再清理。           |
| `agent/`       | Agent 配置、状态与会话历史；按是否需要恢复会话决定保留。                                     |
| `log_dir`      | 带时间戳的日志按 7 天保留策略清理；cron 输出和 daemon 内的日志不属于 Task 日志。             |

delete_entries 接受 JSON paths 数组。这是通用文件能力，不保护活动 Task 进程。删除当前任务目录前停止写入者，检查源身份，并与执行串行协调。删除也移除 persistent/，不会停止进程或重建下游输出。

## 上传与后续消费

POST /upload 或 HttpClient.copy_file 在 `tmp/uploads/` 暂存单文件。StagedFile 包含 path、size、绝对 location。目标机插件安装使用 location，同步和清理使用相对 path。上传不安装文件，插件安装不自动删除暂存文件。应在 finally 清理，详见[上传 API](../api/workspace.md)。

一致性备份见[运维与恢复](../guides/operations.md#备份与恢复)；展示副本会省略数据，不能代替备份。

[Task 契约](../reference/task-contracts.md) · [研究产物](../reference/research-artifacts.md) · [工作区 API](../api/workspace.md)
