# 插件命令与同步 API

插件管理通过通用 `cli` Job 执行，同步保留专用 Job。

遵循 [HTTP/MCP 协议](overview.md)，通过 `axonx help --job NAME` 查询 Schema。示例 Task/会话 ID 需替换为实际值。

## 接口列表

| Job          | 用途                                   |
| ------------ | -------------------------------------- |
| `sync_index` | 读取一个来源已提交的文件清单。         |
| `sync_files` | 提交已暂存的文件批次，不解释文件内容。 |

## sync_index

读取一个同步来源已提交的文件清单。

| 参数     | 类型     | 必填 | 约束                               |
| -------- | -------- | ---- | ---------------------------------- |
| `source` | `string` | 是   | 1–128 个字母、数字、下划线或连字符 |

```json
{
  "arguments": {
    "source": "SOURCE_ID"
  }
}
```

返回 `transfer_budget_bytes` 和 `groups`。每组包含不透明的 `version`、有序整数 `revision` 和 `directories`：工作区相对目录映射到相对文件名及 `{size, revision}` 记录。回执保存在 `sync/receipts/SOURCE_ID.json`。查询只核对一次各落盘目录，并为共享目录返回最新文件清单，避免正常共享更新引发反复重传；缺文件的组会重新传输；不会解析任务元数据或构建任务索引。

发送端使用主机名与工作区路径生成稳定的来源 ID。任务选择、模型筛选和发布时间策略都留在发送端。

## sync_files

提交已暂存的文件批次，不解释文件内容。

| 参数   | 类型     | 必填 | 约束                       |
| ------ | -------- | ---- | -------------------------- |
| `path` | `string` | 是   | 已暂存归档的工作区相对路径 |

```json
{
  "arguments": {
    "path": "tmp/uploads/ACTUAL_UPLOAD_PATH/archive.tar.gz"
  }
}
```

## 文件清单

gzip tar 归档包含 `sync-manifest.json` 和变化文件的内容。清单结构如下：

```json
{
  "source": "SOURCE_ID",
  "groups": {
    "report": {
      "version": "source-publication-version",
      "revision": 1,
      "directories": {
        "tasks/base/base#demo#report": {
          "metadata.json": { "size": 123, "revision": "opaque-file-version" }
        }
      }
    }
  }
}
```

每组声明期望的完整目录清单，也包含没有再次上传的未变文件。目标目录遵循工作区布局 `tasks/TYPE/DIRECTORY` 或 `tmp/tasks/TYPE/DIRECTORY`。接收端仅复用回执匹配的文件，检查路径、大小、压缩及重建预算，并将目录与回执一同提交，失败时回滚。完全相同的批次可重复提交；过期或冲突修订会被拒绝，共享目录也不能回退。

新清单会清理仅由该组拥有的过期目录。`directories` 为空时删除该组文件，并保留修订作为删除记录。其他组仍引用的目录和已有的无归属目录均保留。文件修订是不透明标识，不是内容校验和。

返回 `archive`、`applied`、`deleted` 和 `files`，随后清理暂存上传。已有 `task_index` 扫描器在落盘后发现支持的 `metadata.json`，文件接收不依赖该格式。展示副本保持只读，不能作为研究输入。

## 插件命令

通过 `cli` 传 argv `["plugin", "list"]`、`["plugin", "show", "DISTRIBUTION"]`、`["plugin", "install", "/absolute/upload/location.whl"]` 或 `["plugin", "uninstall", "DISTRIBUTION"]`。响应包含进程 stdout/stderr、exit_code 和截断标志，插件元数据是 stdout 中的 JSON。没有专用插件管理 Job，也不自动刷新常驻目录。从本地部署遵循显式[部署流程](../plugins/management.md)，上传使用 `/upload`。

## sync_flush 的可见性

默认配置注释掉 `sync_flush`，因为它依赖配置好的 sync 组件。仅当组件存在时，用 `backend: sync_flush_step` 暴露 pipeline Job。可手动或由自定义宿主流程调用；Cron 仅支持 Task exec 命令。详见[任务同步](../guides/task-sync.md)。

源码：[默认 Job 契约](../../../axonx/app/config/default.yaml) · [Job 协议](overview.md)
