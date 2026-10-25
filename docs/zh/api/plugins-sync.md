# 插件与同步接口

插件管理统一通过 Plugin CLI，服务只提供通用 `cli` 网关；原 `list_plugins`、`inspect_plugin`、`install_plugin`、`uninstall_plugin` Job 已删除。

```bash
axonx plugin list --target '<host:port>'
axonx plugin install '<上传后返回的 location>' --target '<host:port>'
```

HTTP 调用使用 `POST /jobs/cli`，业务参数为 `{"argv": ["plugin", "list"]}`。返回 `stdout`、`stderr`、`exit_code` 和截断标记。上传、安装和上传文件清理各自独立；安装路径属于目标机器。清理用 `DELETE /upload?path=...`，不再有 staged-install 自动清理旁路。校验、构建和安装均由 `plugin` 模块负责。

见[插件管理](../plugins/management.md)和[Job 调用约定](overview.md)。

## sync_tasks

接收经过校验的展示副本归档并替换目录，或只应用删除。

| 参数        | 类型   | 必填 | 默认值      | 约束与含义                         |
| ----------- | ------ | ---- | ----------- | ---------------------------------- |
| `path`      | string | 否   | `—（省略）` | 服务工作区相对路径；minLength=1    |
| `deletions` | array  | 否   | `[]`        | 待删除的任务目录路径；maxItems=200 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "deletions": []
  }
}
```

**响应**

answer 为 SyncTasksReport：archive、applied、deleted、files。

```json
{
  "answer": {
    "archive": null,
    "applied": [],
    "deleted": [],
    "files": 0
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

path 可省略，deletions 默认为 []，最多 200。path 只接受上传的暂存归档；deletions 是 类型/Task ID 任务目录，不是任意文件路径。接收失败 success=false，answer 是错误文本；归档随后清理。

## 失败响应示例

安装提交的 sha256 格式不合法会返回 HTTP 422；格式正确但制品与哈希不匹配，则安装消费者校验失败并清理暂存文件。再次尝试必须先重新上传。

sync_tasks 对暂存路径/归档的 OSError、TypeError、ValueError 直接返回业务失败文本，例如一个暂存文件不存在：

```json
{ "answer": "Staged file does not exist", "success": false, "metadata": {} }
```

接收端检查目录身份与归档路径，应用替换时保留回滚机制。这里传输的是包含所选发布产物的展示副本，不迁移进程、插件环境、Agent 会话、上游输入或原始数据树。

## task_sync_index

接收可选 `task_names`、`live_task_ids`，返回 `answer.transfer_budget_bytes`、统一的版本及 Run/文件记录映射 `answer.tasks`。`sync_tasks` 接收终态副本或完整在线父子任务组，须保留完整清单并校验差量基底。未标记的源任务归档直接拒绝。本机活跃任务不能被覆盖；在线副本接收同一来源的更新版本。发送端首次 flush 时对账普通任务，每次 flush 捕获在线任务组，不自动传播删除。参见[结果展示同步](../guides/task-sync.md)。

## sync_flush 的可见性

sync_flush 在 default.yaml 中默认被注释；启用示例中的 enable_serve=false 使其只用于内部调度。它不是默认对外 API，不能在 /jobs 中假定存在。结果 SyncReport 含 uploaded、rejected、oversized、deferred、archives，详见 [任务同步](../guides/task-sync.md)。

## 相关文档

- [协议、鉴权与错误](overview.md)
- [插件管理](../plugins/management.md)
- [CLI 参考](../reference/cli.md)
- [事件协议](events.md)

实现依据：`axonx/app/config/default.yaml`、`axonx/cli/plugin.py` 与 `axonx/app/components/service/http/jobs.py`。
