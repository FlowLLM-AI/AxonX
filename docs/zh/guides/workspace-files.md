# 工作区文件

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

## 排障

确认目标、工作区根、精确相对路径、响应限制和副本采样/省略。研究页面要求规范 metadata/产物契约，熟悉文件名本身不足以被识别。

源码：[Workspace](../../../axonx/app/workspace/core.py)、[预览](../../../axonx/app/workspace/preview.py)、[上传](../../../axonx/app/workspace/uploads.py)。
