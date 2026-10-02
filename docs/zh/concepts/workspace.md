# 工作区与持久记录

工作区保存任务状态、成功结果与研究产物，是 Studio 和任务查询共同读取的数据来源。默认根目录为启动目录下的 `.axonx`，可通过 `workspace_dir` 指定绝对路径。日志目录独立配置，默认是 `logs`。

![工作区文件分工](../../figures/concepts/workspace.svg)

## 目录布局

下面是包含 demo 和一个研究插件任务的示意布局，插件文件名以实际产物为准：

```text
.axonx/
  base/
    base#demo#trial-01/
      status.json
      metadata.json
      events.jsonl
  etl/
    etl#my-etl#dataset-01/
      status.json
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

目录规则是 `<task_type>/<task_id>`，不是 `<task_type>/<注册名>/<run_id>`。Task 类型目录来自枚举，某个目录存在并不代表对应算法插件已经安装。

## 三类记录

| 文件          | 何时出现          | 负责什么                                               |
| ------------- | ----------------- | ------------------------------------------------------ |
| status.json   | 受理与运行过程    | run_id、state、步骤、错误、退出码、日志路径、result    |
| metadata.json | 成功时            | 定义身份、创建时间、typed input/output、产物引用与血缘 |
| events.jsonl  | worker 记录进度时 | 按行记录可回放的进度事件                               |

status 是可变快照，metadata 是成功结果封装。它们不是同一内容的两个副本：metadata 不含 `run_id`，status 的 `result` 对应 metadata 的 `output_params`。

记录通过原子写入降低读到半个 JSON 的机会。读取端仍会容忍不合法或与目录身份不一致的记录，把它当成缺失；手工修改文件不应作为常规任务管理方式。

## 产物的相对路径

研究 Task 的 `output_params.artifacts` 可以记录产物：

```json
{
  "artifacts": {
    "dataset": {
      "path": "data/dataset.parquet",
      "size": 10240,
      "sha256": "<文件 SHA-256>"
    }
  }
}
```

这里的 path 相对 Task 目录。因此工作区预览路径为：

```text
etl/etl#my-etl#dataset-01/data/dataset.parquet
```

不能把 artifact 的 path 直接当工作区根路径，也不能用绝对路径或 `../` 逃离任务目录。生产插件应在文件写完后记录 size 和 sha256。

## 日志在哪里

`status.log_path` 记录具体日志位置。日志系统由 `log_dir` 控制，Task 日志不保证固定存在于任务目录中。通过 `read_task_log` 或 Studio 任务详情读取，而不是猜测 `<task_dir>/log.txt`。

`events.jsonl` 是进度事件日志，不等于 Python 文本日志。备份任务目录能保留进度事件，若文本日志放在外部目录，应单独备份。

## 索引与文件的关系

TaskRepository 扫描和监听类型目录下的 status 与 metadata，维护任务查询所需索引。重启可以根据有效文件重新建立索引；它不替你重新训练模型或重新下载原始数据。

任务列表主要依赖状态记录。研究结果列表使用含 metadata 的任务目录，因而成功研究任务、只有 metadata 的迁移记录，以及失败任务在不同入口的可见性可能不同。

## 备份范围

要复现实验，应保留任务目录、原始数据、服务配置、插件版本和模型依赖。Agent 会话、日志和插件源码按实际使用情况单独保留。

停止写入后复制整个工作区最容易得到一致文件。任务同步仅复制终态 Task 目录，不能代替原始数据、Agent 会话、日志与软件环境的完整备份。

固定名称重跑会替换旧目录；删除上游目录会让下游血缘出现 missing 节点，也可能使重跑下游无法读取原始产物。

## 相关文档

[工作区浏览](../guides/workspace-files.md) · [Task 契约](../reference/task-contracts.md) · [研究产物](../reference/research-artifacts.md) · [备份恢复](../guides/operations.md)

源码：[工作区布局](../../../axonx/task/storage/workspace.py)、[元数据](../../../axonx/task/storage/metadata.py)、[产物路径](../../../axonx/task/storage/artifacts.py)。
