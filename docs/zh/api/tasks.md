# 任务 API

Task 通过 `axonx exec` 执行。本 API 只观察已有 Task 的 metadata、日志与关系。使用 metadata 中的 Task ID 与 Run ID 等待某次准确执行。

![任务 API调用示意](../../figures/api/task-call.svg)

## 调用约定

以下均为 `POST /jobs/{name}`，请求体是 `{"arguments":{...}}`。远程转发时在封装顶层添加 `target`，不能放进 arguments。每个响应使用 [JobResponse](overview.md#响应与错误)，表格默认值依据当前内置配置和 Step。部署可修改 Job Schema，运行服务的 `/jobs` 是最终依据。

所有示例 JSON 均为结构示例；任务、会话、文件路径与哈希必须替换为本服务实际返回的值。完整通用 TaskMetadata 字段见 [Task 协议](../reference/task-contracts.md)。

## 接口清单

| Job                               | 用途                                      |
| --------------------------------- | ----------------------------------------- |
| `list_installed_task_definitions` | 枚举当前 Python 环境中的内置与插件 Task。 |
| `get_task_definition`             | 查询一个注册定义及输入输出 Schema。       |
| `wait_task`                       | 等待提交返回的特定执行结束。              |
| `list_task_ids`                   | 列出存在生命周期元数据记录的任务身份。    |
| `list_task_statuses`              | 列出状态快照。                            |
| `status`                          | 读取一个任务的当前状态。                  |
| `read_task_log`                   | 按有界字节窗口读取日志。                  |
| `stream_task`                     | 持续跟踪进度与日志直到任务停止。          |
| `get_task_graph`                  | 读取包含所选 Task 的依赖图。              |
| `get_task_context`                | 为 Agent 提供任务路径、状态与关系上下文。 |

## list_installed_task_definitions

枚举当前 Python 环境中的内置与插件 Task。

可选 `include_schemas`（布尔值，HTTP/MCP 默认 `true`）控制是否生成输入/输出 schema。CLI 默认 `--include-schemas false`；选定 Task 后通过 `get_task_definition` 获取单个定义，或显式传 `--include-schemas true` 获取完整目录。

**请求**

```json
{
  "arguments": {}
}
```

**响应**

`answer` 按名称排序，每项包含 `name`、`source`（`native`/`plugin`）、`plugin`、`category`、`task_type` 和 `description`。仅 `include_schemas=true` 时返回 `input_schema`、`output_schema`；轻量查询不会生成 schema。

```json
{
  "answer": [],
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

输出按注册名排序。某个插件类型错误可能使完整目录查询失败。缺少或仅含空白的类 docstring 返回空 description，当前 Task 和其他任务列表项仍可正常展示。

## get_task_definition

查询一个注册定义及输入输出 Schema。

| 参数   | 类型   | 必填 | 默认值      | 约束与含义                             |
| ------ | ------ | ---- | ----------- | -------------------------------------- |
| `task` | string | 是   | `—（省略）` | Task 注册名，不是 Task ID；minLength=1 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "task": "demo"
  }
}
```

**响应**

answer 是一个 TaskDefinition；Schema 是 JSON Schema，不是任务执行结果。

```json
{
  "answer": {
    "name": "demo",
    "source": "native",
    "plugin": null,
    "task_type": "base",
    "description": "Demonstrate synchronous Task execution with a small arithmetic workflow.",
    "input_schema": {
      "type": "object",
      "required": ["x", "y"]
    },
    "output_schema": {
      "type": "object"
    }
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

上面的 Schema 为节选；完整 Schema 以接口返回为准。未知注册名返回业务失败。

## wait_task

等待提交返回的特定执行结束。

| 参数            | 类型   | 必填 | 默认值      | 约束与含义                                    |
| --------------- | ------ | ---- | ----------- | --------------------------------------------- |
| `task_id`       | string | 是   | `—（省略）` | 完整 Task ID；minLength=1                     |
| `run_id`        | string | 是   | `—（省略）` | 提交返回的本次执行 ID；minLength=1            |
| `poll_interval` | number | 否   | `1`         | 轮询间隔，单位秒；exclusiveMinimum=0          |
| `detail`        | string | 否   | `full`      | `summary` 或 `full`；CLI 默认请求 `summary`。 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23"
  }
}
```

**响应**

`detail=summary` 使用与 `list_task_statuses` 相同的有界摘要，保留 Task/Run ID、生命周期状态和管理器归属；输入、输出、子任务和完整错误需 `detail=full`。返回摘要时，`wait_task.success` 仍由 Task 的终态决定。

`detail=full` 时，`answer` 是终态 TaskMetadata；只有 state=succeeded 时 success=true。

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task_type": "base",
    "state": "succeeded",
    "created_at": "2026-10-02T00:00:00Z",
    "started_at": null,
    "finished_at": null,
    "pid": null,
    "exit_code": 0,
    "error": "",
    "steps": [],
    "log_path": "",
    "input_params": {
      "task_name": "api-demo",
      "source_tasks": "",
      "x": 1,
      "y": 2,
      "fail": false
    },
    "output_params": {},
    "reg_name": "demo",
    "children": []
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

poll_interval 默认 1 秒，没有业务超时参数。客户端 timeout 应覆盖等待时间。run_id 与目录当前执行不一致时失败，不能用旧 run_id 等待新任务。

## list_task_ids

列出存在生命周期元数据记录的任务身份。

无公开业务参数；使用 `{"arguments":{}}`。

**请求**

```json
{
  "arguments": {}
}
```

**响应**

answer 是字符串 Task ID 数组。

```json
{
  "answer": ["base#demo#api-demo"],
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

只索引有效的统一 metadata 记录；列表不是全历史执行清单。

## list_task_statuses

列出完整状态快照或轻量摘要。

可选参数 `detail`：`summary`（默认）或 `full`（显式获取完整快照）。Studio 列表使用 `summary`。

```json
{ "arguments": { "detail": "summary" } }
```

**请求**

```json
{
  "arguments": {}
}
```

**响应**

`answer` 按 `created_at` 与 `task_id` 倒序。`full` 返回原有完整 TaskMetadata；`summary` 返回 `task_id`、`run_id`、`task_type`、`reg_name`、`state`、`pid`、`created_at`、`started_at`、`finished_at`、`exit_code`、`log_path` 和 `error`（最多 1,000 字符）。

摘要省略 `input_params`、`output_params`、`children` 和 `steps`，增加 `display_name`（配置中的任务名称或注册名称，最多 256 字符）、`is_online`（是否属于在线流水线）和 `step_progress`：无步骤时为 `null`，否则为 `{current, total, name, percentage}`。步骤序号从 1 开始，选择首个未完成步骤，全部完成时选择最后一步。名称最多 256 字符，百分比可以为 `null`。完整详情通过 `status` 读取。

```json
{
  "answer": [],
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

不提供服务器分页与筛选参数。客户端可以按类型和状态筛选；按配置筛选需要使用 `full`。无效的 `detail` 值会被参数校验拒绝。

## status

读取一个任务的当前状态。

| 参数      | 类型   | 必填 | 默认值      | 约束与含义                                    |
| --------- | ------ | ---- | ----------- | --------------------------------------------- |
| `task_id` | string | 是   | `—（省略）` | 完整 Task ID                                  |
| `detail`  | string | 否   | `full`      | `summary` 或 `full`；CLI 默认请求 `summary`。 |

Schema 未禁止额外字段；不要据此假定额外字段会被使用。

**请求**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**响应**

`detail=summary` 使用与 `list_task_statuses` 相同的有界摘要，保留 Task/Run ID、生命周期状态和管理器归属；输入、输出、子任务和完整错误需 `detail=full`。查询成功与 Task 成功仍是不同概念。

answer 是 TaskMetadata：身份、input_params、output_params、children、state、时间、pid、exit_code、error、steps、log_path。

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task_type": "base",
    "state": "queued",
    "created_at": "2026-10-02T00:00:00Z",
    "started_at": null,
    "finished_at": null,
    "pid": null,
    "exit_code": 0,
    "error": "",
    "steps": [],
    "log_path": "",
    "input_params": {
      "task_name": "api-demo",
      "source_tasks": "",
      "x": 1,
      "y": 2,
      "fail": false
    },
    "output_params": {},
    "reg_name": "demo",
    "children": []
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

没有有效统一 metadata 的任务返回 KeyError 业务失败。queued/running 不是终态。

## read_task_log

按有界字节窗口读取日志。

| 参数      | 类型    | 必填 | 默认值      | 约束与含义                                    |
| --------- | ------- | ---- | ----------- | --------------------------------------------- |
| `task_id` | string  | 是   | `—（省略）` | 完整 Task ID                                  |
| `run_id`  | string  | 否   | —           | 可选的准确 Run ID；读取前拒绝已替换的运行。   |
| `offset`  | integer | 否   | `-1`        | 日志读取起始字节偏移；-1 读取尾部；minimum=-1 |
| `limit`   | integer | 否   | `8192`      | 最多读取的字节数；minimum=1, maximum=262144   |

Schema 未禁止额外字段；不要据此假定额外字段会被使用。

**请求**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo",
    "offset": -1,
    "limit": 65536
  }
}
```

**响应**

answer 是 LogChunk：content、start_offset、next_offset、file_size、has_more_before、has_more_after、reset。

```json
{
  "answer": {
    "content": "Demo result=3\n",
    "start_offset": 0,
    "next_offset": 14,
    "file_size": 14,
    "has_more_before": false,
    "has_more_after": false,
    "reset": false
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

offset=-1 读取尾部；offset=0 从头开始。limit 单位字节，不是行数。UTF-8 解码后字符串长度不能代替 next_offset；持续读取用返回的 next_offset。

## stream_task

持续跟踪进度与日志直到任务停止。

| 参数            | 类型   | 必填 | 默认值      | 约束与含义                           |
| --------------- | ------ | ---- | ----------- | ------------------------------------ |
| `task_id`       | string | 是   | `—（省略）` | 完整 Task ID；minLength=1            |
| `poll_interval` | number | 否   | `0.5`       | 轮询间隔，单位秒；exclusiveMinimum=0 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**响应**

普通调用 answer 是终态 TaskMetadata；SSE 有 progress/log，最终 result 携带相同状态。success 按 exit_code==0 设置。

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task_type": "base",
    "state": "succeeded",
    "created_at": "2026-10-02T00:00:00Z",
    "started_at": null,
    "finished_at": null,
    "pid": null,
    "exit_code": 0,
    "error": "",
    "steps": [],
    "log_path": "",
    "input_params": {
      "task_name": "api-demo",
      "source_tasks": "",
      "x": 1,
      "y": 2,
      "fail": false
    },
    "output_params": {},
    "reg_name": "demo",
    "children": []
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

默认 poll_interval=0.5 秒。普通 HTTP 调用也会等待到终态，日志事件不会全部装进 answer；实时显示应使用 /events。

## get_task_graph

读取包含所选 Task 的依赖图。

| 参数      | 类型   | 必填 | 默认值      | 约束与含义   |
| --------- | ------ | ---- | ----------- | ------------ |
| `task_id` | string | 是   | `—（省略）` | 完整 Task ID |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**响应**

answer 含 root_id、selected_id、nodes、edges；节点区分 missing、provisional。

```json
{
  "answer": {
    "root_id": "base#demo#api-demo",
    "selected_id": "base#demo#api-demo",
    "nodes": [
      {
        "task_id": "base#demo#api-demo",
        "kind": "base",
        "task_name": "demo",
        "created_at": "2026-10-02T00:00:00+00:00",
        "parent_ids": [],
        "state": "queued",
        "missing": false,
        "provisional": true
      }
    ],
    "edges": []
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

图来自 metadata.input_params.source_tasks，只呈现记录关系，不会执行 DAG。节点结构详见任务血缘文档；此例仅展示顶层形状。

## get_task_context

为 Agent 提供任务路径、状态与关系上下文。

| 参数      | 类型   | 必填 | 默认值      | 约束与含义                |
| --------- | ------ | ---- | ----------- | ------------------------- |
| `task_id` | string | 是   | `—（省略）` | 完整 Task ID；minLength=1 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**响应**

answer 含 task_id、status、metadata_exists、metadata_path、log_path、graph、relations。relations 包括 direct_upstream、ancestors、direct_downstream、missing、provisional。

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "status": {
      "task_id": "base#demo#api-demo",
      "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
      "task_type": "base",
      "state": "queued",
      "created_at": "2026-10-02T00:00:00Z",
      "started_at": null,
      "finished_at": null,
      "pid": null,
      "exit_code": 0,
      "error": "",
      "steps": [],
      "log_path": "",
      "input_params": {
        "task_name": "api-demo",
        "source_tasks": "",
        "x": 1,
        "y": 2,
        "fail": false
      },
      "output_params": {},
      "reg_name": "demo",
      "children": []
    },
    "metadata_exists": true,
    "metadata_path": "base/base#demo#api-demo/metadata.json",
    "log_path": null,
    "graph": {
      "root_id": "base#demo#api-demo",
      "selected_id": "base#demo#api-demo",
      "nodes": [
        {
          "task_id": "base#demo#api-demo",
          "kind": "base",
          "task_name": "demo",
          "created_at": "2026-10-02T00:00:00+00:00",
          "parent_ids": [],
          "state": "queued",
          "missing": false,
          "provisional": true
        }
      ],
      "edges": []
    },
    "relations": {
      "direct_upstream": [],
      "ancestors": [],
      "direct_downstream": [],
      "missing": [],
      "provisional": ["base#demo#api-demo"]
    }
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

metadata_exists 表示当前有效生命周期记录存在；研究是否成功应另行检查 state 和产物。

## 失败响应示例

Schema 失败在执行前返回 HTTP 422，例如 wait_task 缺 run_id；Task 执行或查询异常通常返回 HTTP 200 与 success=false。未知 Task 注册名示例：

```json
{
  "answer": "ValueError: Unknown Task: missing. Available: demo",
  "success": false,
  "metadata": {}
}
```

Available 列表由实际安装环境生成。wait_task 返回失败任务状态时 answer 仍是 TaskMetadata，state=failed，并保留 error 与 exit_code；不能假定失败 answer 永远是字符串。

## 相关文档

- [协议、鉴权与错误](overview.md)
- [任务执行与管理](../guides/task-management.md)
- [CLI 参考](../reference/cli.md)
- [事件协议](events.md)

实现依据：`axonx/config/default.yaml`、`axonx/app/steps/task/` 与 `axonx/app/components/service/http/jobs.py`。

## Studio 查询投影

`detail: summary` 返回生成的 `TaskSummary` 契约。摘要只在查询时投影，
不会另存一份 Task 记录。研究和策略比较列表请求摘要，仅对选中的 Task
通过 `status` 加载详情。完整输出、训练曲线和产物注册表属于详情响应。
任务图直接从仓库快照构建，不复制 Task 的完整输出。

Studio 的传输类型从 Python 契约生成，覆盖摘要、任务图、Job 事件和
Agent 会话展示。研究输出按 `task_type` 区分；在线执行窗口与预测比较
保留各自的状态枚举。修改接口时更新 Python 契约，再从 `axonx_studio/`
运行 `npm run contracts:generate`。
