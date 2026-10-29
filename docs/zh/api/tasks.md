# Task 执行与观察 API

执行通过原生 CLI 或服务拥有的 `cli` 命令 Job，观察读取持久化 Task 记录。

遵循 [HTTP/MCP 协议](overview.md)，通过 `axonx help --job NAME` 查询 Schema。示例 Task/会话 ID 需替换为实际值。

## 接口列表

| Job                  | 用途                                                                                        |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `cli`                | 在本服务机器的子进程中执行 AxonX CLI 命令。路径属于目标机器，不支持启动服务或嵌套远程转发。 |
| `list_task_defs`     | 列出本服务 Python 环境中注册的 Task，可省略 Schema 以减少响应体积。                         |
| `get_task_def`       | 查询本服务中某个注册 Task 的说明及输入输出 Schema。                                         |
| `wait_task`          | 等待当前 Task 执行结束；等待期间发现重跑则报错。                                            |
| `list_task_ids`      | 列出索引中具有有效 metadata.json 的 Task ID。                                               |
| `list_task_statuses` | 按类型和状态筛选 Task，返回轻量摘要或完整元数据快照。                                       |
| `status`             | 读取一个 Task 的当前状态。                                                                  |
| `read_task_log`      | 按字节范围读取一个 Task 的日志。                                                            |
| `stream_task`        | 持续传输一个 Task 的进度和日志，直到执行结束。                                              |
| `get_task_graph`     | 返回包含所选 Task 的输入依赖连通图。                                                        |
| `get_task_context`   | 返回当前 Task 元数据、元数据路径、输入依赖图与上下游关系。                                  |

## cli

在本服务机器的子进程中执行 AxonX CLI 命令。路径属于目标机器，不支持启动服务或嵌套远程转发。

| 参数   | 类型    | 必填 | 默认/约束        |
| ------ | ------- | ---- | ---------------- |
| `argv` | `array` | 是   | `{"minItems":1}` |

```json
{
  "arguments": {
    "argv": [
      "exec",
      "--task",
      "demo",
      "--task-name",
      "api-check",
      "--x",
      "1",
      "--y",
      "2"
    ]
  }
}
```

在服务工作区不经 shell 执行 argv，使用配置的命令/解释器并拥有子进程组。返回 stdout、stderr、exit_code 和各通道截断标志（各通道在结果中最多保留前 1 MiB），日志事件区分 stdout/stderr。断开/取消可能终止所属进程组，拒绝嵌套转发和启动服务。安装已上传 wheel 使用 argv `["plugin", "install", absolute_location]`。

## list_task_defs

列出本服务 Python 环境中注册的 Task，可省略 Schema 以减少响应体积。

| 参数              | 类型      | 必填 | 默认/约束          |
| ----------------- | --------- | ---- | ------------------ |
| `include_schemas` | `boolean` | 否   | `{"default":true}` |

```json
{
  "arguments": {
    "include_schemas": false
  }
}
```

读取常驻服务目录，`include_schemas=false` 省略 Schema，但仍解析已注册类。安装新插件不重建启动快照。

## get_task_def

查询本服务中某个注册 Task 的说明及输入输出 Schema。

| 参数   | 类型     | 必填 | 默认/约束         |
| ------ | -------- | ---- | ----------------- |
| `task` | `string` | 是   | `{"minLength":1}` |

```json
{
  "arguments": {
    "task": "demo"
  }
}
```

返回一个注册的 name、source、plugin、task_type、description、input_schema 和 output_schema。

## wait_task

等待当前 Task 执行结束；等待期间发现重跑则报错。

| 参数            | 类型     | 必填 | 默认/约束                                      |
| --------------- | -------- | ---- | ---------------------------------------------- |
| `task_id`       | `string` | 是   | `{"minLength":1}`                              |
| `poll_interval` | `number` | 否   | `{"exclusiveMinimum":0,"default":1}`           |
| `detail`        | `string` | 否   | `{"enum":["summary","full"],"default":"full"}` |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check",
    "poll_interval": 1,
    "detail": "full"
  }
}
```

捕获当前 started_at，等待期间若重跑则拒绝继续。返回摘要或完整 metadata，只有 succeeded 时 success 为 true。没有业务超时入参，应设置足够的客户端超时。

## list_task_ids

列出索引中具有有效 metadata.json 的 Task ID。

无业务参数。

```json
{
  "arguments": {}
}
```

## list_task_statuses

按类型和状态筛选 Task，返回轻量摘要或完整元数据快照。

| 参数        | 类型     | 必填 | 默认/约束                                               |
| ----------- | -------- | ---- | ------------------------------------------------------- |
| `detail`    | `string` | 否   | `{"enum":["summary","full"],"default":"summary"}`       |
| `task_type` | `string` | 否   | `—`                                                     |
| `state`     | `string` | 否   | `{"enum":["running","succeeded","failed","cancelled"]}` |

```json
{
  "arguments": {
    "detail": "summary"
  }
}
```

两种 detail 都返回按创建时间倒序、以 Task ID 作为次排序键的列表，完整记录在筛选后才复制。`summary` 包含 TaskStatus 字段，以及 `display_name`、`is_replica` 和可选 `step_progress`（`current`、`total`、`name`、`percentage`），省略输入、输出、步骤和子调用数组。摘要错误最多 1000 字符，显示名称和步骤名最多 256 字符。列表使用周期刷新的索引（默认 5 秒）；`status` 和 `wait_task` 直接读取所选 metadata。

## status

读取一个 Task 的当前状态。

| 参数      | 类型     | 必填 | 默认/约束                                      |
| --------- | -------- | ---- | ---------------------------------------------- |
| `detail`  | `string` | 否   | `{"enum":["summary","full"],"default":"full"}` |
| `task_id` | `string` | 是   | `—`                                            |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check",
    "detail": "full"
  }
}
```

读取当前 metadata 或摘要。查询不修正失效 running 记录，应将 started_at 与所观察执行比较。

## read_task_log

按字节范围读取一个 Task 的日志。

| 参数         | 类型      | 必填 | 默认/约束                                       |
| ------------ | --------- | ---- | ----------------------------------------------- |
| `task_id`    | `string`  | 是   | `—`                                             |
| `started_at` | `string`  | 否   | `{"format":"date-time"}`                        |
| `offset`     | `integer` | 否   | `{"minimum":-1,"default":-1}`                   |
| `limit`      | `integer` | 否   | `{"minimum":1,"maximum":262144,"default":8192}` |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check",
    "offset": -1,
    "limit": 8192
  }
}
```

返回 content、start_offset、next_offset、file_size、has_more_before、has_more_after、reset，并发布 log 事件。可选 started_at 在读取前拒绝替换执行，游标按字节计。

## stream_task

持续传输一个 Task 的进度和日志，直到执行结束。

| 参数            | 类型     | 必填 | 默认/约束                              |
| --------------- | -------- | ---- | -------------------------------------- |
| `task_id`       | `string` | 是   | `{"minLength":1}`                      |
| `poll_interval` | `number` | 否   | `{"exclusiveMinimum":0,"default":0.5}` |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check"
  }
}
```

传输进度/日志，终态 result 返回当前 metadata，观察到重跑会报错；订阅不会启动 Task。

## get_task_graph

返回包含所选 Task 的输入依赖连通图。

| 参数      | 类型     | 必填 | 默认/约束 |
| --------- | -------- | ---- | --------- |
| `task_id` | `string` | 是   | `—`       |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check"
  }
}
```

返回输入依赖连通图的 `root_id`、`selected_id`、`nodes` 和有向 `edges`（`from` → `to`）。边仅来自 `input_params.upstream_task_ids`；父子调用保存在 Task metadata 中。`missing` 表示引用记录不可用，`provisional` 表示记录存在但状态不是 `succeeded`。查询不执行依赖。

## get_task_context

返回当前 Task 元数据、元数据路径、输入依赖图与上下游关系。

| 参数      | 类型     | 必填 | 默认/约束         |
| --------- | -------- | ---- | ----------------- |
| `task_id` | `string` | 是   | `{"minLength":1}` |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check"
  }
}
```

返回 `task_id`、完整 `status`（TaskMetadata）、工作区相对 `metadata_path`、`graph` 和 `relations`。关系包含 `direct_upstream`、`all_upstream`、`direct_downstream`、`missing`、`provisional`。所选记录实时读取，其余图节点来自当前索引快照。输入、输出与子调用记录完整返回，接口不提供按字节截断的上下文摘要。

## 结果与生命周期

TaskMetadata 包含 task_id、task_type、reg_name、parent_task_id、report_kind、state、进程身份、started_at、输入输出、步骤、子任务及可选展示副本信息。实际 Task 状态为 running/succeeded/failed；状态筛选 Schema 还声明了当前 Task 模型不产生的取消状态值。摘要省略较大的业务输入输出。

停止使用 `cli` 的 `["kill", "--task-id", "ID"]`。执行停止后通过通用 `delete_entries` 清理目录，没有专门的 Task 删除 Job。详见 [Task 契约](../reference/task-contracts.md)。

源码：[默认 Job 契约](../../../axonx/app/config/default.yaml) · [Job 协议](overview.md)
