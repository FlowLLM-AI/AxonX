# 工作区浏览与预览

文件能力以配置的工作区为根，只接收工作区相对路径。先列目录定位记录，再预览格式，最后按需要清理。Studio 的工作区入口浏览配置的整个 `workspace_dir`，包括数据、Task 产物、Agent 文件、日志、插件与临时文件。目录按需加载，不限定数据源，也不采用数据源专属排序。

## 浏览目录

```bash
axonx list_entries
axonx list_entries --path base
axonx list_entries --path 'base/base#demo#add-01'
axonx list_task_runs --task-type train
```

空 path 表示工作区根。目录列表优先展示目录，并按名称排序；单次最多 5000 项。truncated 为 true 时，将已读取条目数作为 offset 请求下一页；Studio 提供“加载更多条目”按钮。它不是递归文件树。

`list_task_runs` 筛选具有 metadata.json 的任务目录。若任务 failed 或仍在 running，通常不会在这里出现；请使用任务状态查询确认执行。

路径不能借助绝对路径、`..` 或符号链接逃离工作区。目录项中可显示 symlink，但不应把它当成可预览的普通文件。

## 预览记录与产物

```bash
axonx preview_file --path 'base/base#demo#add-01/status.json'
axonx preview_file --path 'base/base#demo#add-01/metadata.json'
```

预览响应包含文件大小、格式类型和格式对应内容。JSON/YAML 的 data 是结构化对象；解析失败时应检查 parse_error，而不是直接假设文件无数据。

产物路径相对任务目录。若 metadata 中 `artifacts.dataset.path` 为 `data/features.parquet`，完整预览 path 应组合为：

```text
etl/<ETL Task ID>/data/features.parquet
```

## 格式与限制

| 格式              | 返回内容                 | 限制                             |
| ----------------- | ------------------------ | -------------------------------- |
| txt               | UTF-8 文本前缀           | 最多 512 KiB，标记 truncated     |
| md / markdown     | 正文与 frontmatter       | 同上，frontmatter_error 单独记录 |
| json / yaml / yml | 解析内容与结构化 data    | 超过 32 MiB 返回限制提示         |
| csv               | 列名与行窗口             | offset/limit 控制行数            |
| parquet           | 列、类型、总行数与行窗口 | offset/limit 控制行数            |
| 其他扩展名        | unsupported 与大小       | 不自动解码模型、压缩包或图片     |

文本默认按 UTF-8（支持 BOM）解析。二进制文件改后缀为 txt 不会使其变成有效文本。

Studio 的工作区页面可预览任意工作区目录内的支持格式文件。CSV 与 Parquet 使用每页 200 行的窗口；JSON、YAML、Markdown 与文本使用相同的有界预览接口。点击工作区根节点标题可返回根目录。符号链接会显示但无法打开；不支持的格式显示文件大小和无法预览的提示。

![工作区浏览器预览研究产物（Playground 虚构数据）](../../figures/studio/workspace-preview.jpg)

## 行分页

```bash
axonx preview_file --path 'tushare/2026/20260105/daily.parquet' \
  --offset 0 --limit 200
axonx preview_file --path 'tushare/2026/20260105/daily.parquet' \
  --offset 200 --limit 200
```

路径仅为常见原始数据示例，应先用 `list_entries` 选择实际文件。offset 是跳过的数据行数，limit 为 1–5000，默认 200。

这些参数适用于 CSV/Parquet，不是 JSON 文本的字节偏移。目录分页也使用 offset，但计数单位是目录条目而不是数据行。任务日志使用另一个接口，其 offset 是字节单位。

研究大文件时，预览用于快速检查 Schema、日期和少量样本；完整统计应由本机脚本或研究 Task 读取完整文件。仅凭首屏不能判断全数据不存在缺失值。

## 清理文件与目录

```bash
axonx delete_entries --paths '["temporary/report.txt"]'
```

这是删除示例，先确认路径存在且不再需要。接口一次接受 1–200 个路径，先验证选择，再删除最上层根；同时选择父目录和子文件时，不会重复删除子项。

`delete_entries` 是通用文件能力，不具备 TaskManager 的活跃任务保护。清理整个 Task 应优先使用 `delete_tasks`，避免直接删除正在写入的目录。

工作区根不允许删除，目录删除是递归删除。路径限制防止离开工作区，不等于撤销或回收站；需要保留的产物先备份。

## 上传与后续消费

插件安装和同步使用 `/files` 以原始二进制或 multipart 格式暂存制品，返回 FileCopy 中的 path、size、sha256。接收方消费的是返回的工作区相对路径，而非客户端源路径。

上传不是通用目录镜像。消费成功后应清理暂存文件，具体过程见[文件传输 API](../api/workspace.md)。

## 排查显示异常

| 现象               | 检查                                                |
| ------------------ | --------------------------------------------------- |
| 文件不在列表中     | 执行机器、工作区根、目录层级、truncated             |
| JSON 无结构化 data | parse_error 或文件超过结构化预览预算                |
| 表格只显示部分行   | offset、limit、Parquet 的 row_count 与 has_more     |
| 研究页没有产物     | metadata 是否存在、artifact path 是否相对 Task 目录 |

[工作区概念](../concepts/workspace.md) · [研究产物协议](../reference/research-artifacts.md) · [Workspace API](../api/workspace.md)

源码：[目录操作](../../../axonx/workspace/browser.py)、[预览实现](../../../axonx/workspace/preview.py)、[路径约束](../../../axonx/workspace/paths.py)。
