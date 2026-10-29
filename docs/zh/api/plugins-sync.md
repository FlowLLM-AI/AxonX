# 插件命令与同步 API

插件管理通过通用 `cli` Job 执行，同步保留专用 Job。

遵循 [HTTP/MCP 协议](overview.md)，通过 `axonx help --job NAME` 查询 Schema。示例 Task/会话 ID 需替换为实际值。

## 接口列表

| Job               | 用途                                                                                                            |
| ----------------- | --------------------------------------------------------------------------------------------------------------- |
| `task_sync_index` | 读取经核验的展示副本版本，供同步对账。                                                                          |
| `sync_tasks`      | 从已上传的同步归档替换 Task 目录，可同时应用删除操作；替换任务组还会移除同一来源/根任务组中不再包含的展示副本。 |

## task_sync_index

读取经核验的展示副本版本，供同步对账。

| 参数            | 类型    | 必填 | 默认/约束 |
| --------------- | ------- | ---- | --------- |
| `root_task_ids` | `array` | 否   | `[]`      |

```json
{
  "arguments": {
    "root_task_ids": ["base#research#experiment"]
  }
}
```

返回用于对账的已核验展示快照修订。`root_task_ids` 按根 Task ID 选择工作流任务组，空列表或省略时包含全部组。快照身份使用 `root_started_at` 和有序 revision；模型筛选由发送端的 `model_names` 与 `rules` 配置完成。

## sync_tasks

从已上传的同步归档替换 Task 目录，可同时应用删除操作；替换任务组还会移除同一来源/根任务组中不再包含的展示副本。

| 参数        | 类型     | 必填 | 默认/约束                       |
| ----------- | -------- | ---- | ------------------------------- |
| `path`      | `string` | 否   | `{"minLength":1}`               |
| `deletions` | `array`  | 否   | `{"maxItems":200,"default":[]}` |

```json
{
  "arguments": {
    "path": "tmp/uploads/ACTUAL_UPLOAD_PATH/archive.tar.gz"
  }
}
```

应用已上传同步归档和可选删除项。此处使用上传的相对 path，不是插件安装用的绝对 location；返回 `archive`、`applied`、`deleted` 和 `files`。gzip tar 归档必须在规范 Task 目录中包含经核验的展示副本 metadata 和普通文件，并受传输预算限制；应用时拒绝覆盖活动的原始 Task 目录。展示副本仅用于检查，不能执行或作为研究输入。

## 插件命令

通过 `cli` 传 argv `["plugin", "list"]`、`["plugin", "show", "DISTRIBUTION"]`、`["plugin", "install", "/absolute/upload/location.whl"]` 或 `["plugin", "uninstall", "DISTRIBUTION"]`。响应包含进程 stdout/stderr、exit_code 和截断标志，插件元数据是 stdout 中的 JSON。没有专用插件管理 Job，也不自动刷新常驻目录。从本地部署遵循显式[部署流程](../plugins/management.md)，上传使用 `/upload`。

## sync_flush 的可见性

默认配置注释掉 `sync_flush`，因为它依赖配置好的 sync 组件。仅当组件存在时，用 `backend: sync_flush_step` 暴露 pipeline Job。可手动或由自定义宿主流程调用；Cron 仅支持 Task exec 命令。详见[任务同步](../guides/task-sync.md)。

源码：[默认 Job 契约](../../../axonx/app/config/default.yaml) · [Job 协议](overview.md)
