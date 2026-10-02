# Task API

Task submission, status, logs, and lineage queries share the Job protocol. Query a registered definition before submitting inputs; use task_id and run_id to wait for a particular execution.

![Task API call flow](../../figures/api/task-call.svg)

## Calling conventions

All endpoints below use `POST /jobs/{name}` with a `{"arguments":{...}}` request body. For remote forwarding, add `target` at the envelope's top level, outside arguments. Every response uses [JobResponse](overview.md#responses-and-errors). Table defaults come from the current built-in configuration and Steps. Deployments may change Job Schemas; the running service's `/jobs` is authoritative.

All JSON examples illustrate structure; replace task IDs, session IDs, file paths, and hashes with values actually returned by your service. See [Task contracts](../reference/task-contracts.md) for the complete shared TaskStatus fields.

## Endpoint list

| Job | Purpose |
| --- | --- |
| `list_installed_task_definitions` | Enumerate built-in and plugin Tasks in the current Python environment. |
| `get_task_definition` | Query a registered definition and its input/output Schemas. |
| `submit` | Start a separate subprocess to run a Task. |
| `wait_task` | Wait for the specific execution returned by submission to finish. |
| `list_task_ids` | List task identities with status files. |
| `list_task_statuses` | List status snapshots. |
| `status` | Read a task's current status. |
| `read_task_log` | Read logs within a bounded byte window. |
| `stream_task` | Follow progress and logs until the task stops. |
| `get_task_graph` | Read the dependency graph containing the selected Task. |
| `get_task_context` | Provide the Agent with task paths, status, and relationship context. |
| `cancel` | Request cancellation of an active worker managed by this service. |
| `delete_tasks` | Delete terminal or metadata-only Tasks and associated files. |

## list_installed_task_definitions

Enumerate built-in and plugin Tasks in the current Python environment.

No public business parameters; use `{"arguments":{}}`.

**Request**

```json
{
  "arguments": {}
}
```

**Response**

answer is an array of TaskDefinition. Each item contains name, source (native/plugin), plugin, task_type, description, input_schema, and output_schema.

```json
{
  "answer": [],
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Output is sorted by registration name. An invalid plugin type or missing detailed class docstring may cause the full catalog query to fail.

## get_task_definition

Query a registered definition and its input/output Schemas.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task` | string | Yes | `— (omitted)` | Task registration name, rather than a Task ID; minLength=1 |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "task": "demo"
  }
}
```

**Response**

answer is a TaskDefinition; the Schemas are JSON Schemas, rather than task execution results.

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
      "required": [
        "x",
        "y"
      ]
    },
    "output_schema": {
      "type": "object"
    }
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

The Schema above is an excerpt; the complete Schema is authoritative as returned by the endpoint. An unknown registration name returns a business failure.

## submit

Start a separate subprocess to run a Task.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task` | string | Yes | `— (omitted)` | Task registration name, rather than a Task ID |

The submit Schema allows extra fields. Fields other than task are passed as Task inputs and validated by the corresponding input_cls; unknown input fields fail.

**Request**

```json
{
  "arguments": {
    "task": "demo",
    "task_name": "api-demo",
    "x": 1,
    "y": 2
  }
}
```

**Response**

answer is TaskHandle: task_id, run_id, and task. success=true means submission succeeded.

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task": "demo"
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Pass all Task input fields at the same level as task. For demo, x and y are required and fail=false.

Shared Task inputs are published alongside the specific Task's input_schema:

| Input | Type | Default | Rules |
| --- | --- | --- | --- |
| task_name | string/null | null | Omission or an empty string generates an anonymous name; fixed names contain 1–32 English letters, digits, or hyphens |
| source_tasks | string | Empty string | Full upstream Task IDs separated by ASCII commas; not an array of strings |
| demo.x / demo.y | integer | Required | Two calculation inputs; submit as x/y without the demo prefix |
| demo.fail | boolean | false | Built-in failure-demonstration switch; not a shared parameter for all Tasks |

Use get_task_definition for a plugin Task's research parameters; do not apply demo fields to other registration names. The shared task_name is optional and source_tasks defaults to an empty string. Fixed names may replace only finished tasks; an active directory produces FileExistsError. Retain run_id.

## wait_task

Wait for the specific execution returned by submission to finish.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_id` | string | Yes | `— (omitted)` | Full Task ID; minLength=1 |
| `run_id` | string | Yes | `— (omitted)` | Execution ID returned by submission; minLength=1 |
| `poll_interval` | number | No | `1` | Polling interval in seconds; exclusiveMinimum=0 |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23"
  }
}
```

**Response**

answer is a terminal TaskStatus; success=true only when state=succeeded.

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task_type": "base",
    "task_name": "demo",
    "state": "succeeded",
    "config": {
      "task_name": "api-demo",
      "source_tasks": "",
      "x": 1,
      "y": 2,
      "fail": false
    },
    "created_at": "2026-10-02T00:00:00Z",
    "started_at": null,
    "finished_at": null,
    "pid": null,
    "exit_code": 0,
    "error": "",
    "result": {},
    "steps": [],
    "log_path": ""
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

poll_interval defaults to 1 second; there is no business timeout parameter. The client timeout should cover the wait. A run_id that differs from the directory's current execution fails; an old run_id cannot wait for a new task.

## list_task_ids

List task identities with status files.

No public business parameters; use `{"arguments":{}}`.

**Request**

```json
{
  "arguments": {}
}
```

**Response**

answer is an array of Task ID strings.

```json
{
  "answer": [
    "base#demo#api-demo"
  ],
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Metadata-only directories without status do not appear in this list; it is not a complete historical execution list.

## list_task_statuses

List status snapshots.

No public business parameters; use `{"arguments":{}}`.

**Request**

```json
{
  "arguments": {}
}
```

**Response**

answer is an array of TaskStatus, sorted by created_at and task_id in descending order.

```json
{
  "answer": [],
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

No server-side pagination or filtering parameters are provided. Clients can filter by type, state, and configuration as needed.

## status

Read a task's current status.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_id` | string | Yes | `— (omitted)` | Full Task ID |

The Schema does not prohibit extra fields; this does not mean those fields will be used.

**Request**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**Response**

answer is TaskStatus: identity, config, state, timestamps, pid, exit_code, error, steps, and log_path.

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task_type": "base",
    "task_name": "demo",
    "state": "queued",
    "config": {
      "task_name": "api-demo",
      "source_tasks": "",
      "x": 1,
      "y": 2,
      "fail": false
    },
    "created_at": "2026-10-02T00:00:00Z",
    "started_at": null,
    "finished_at": null,
    "pid": null,
    "exit_code": 0,
    "error": "",
    "result": {},
    "steps": [],
    "log_path": ""
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

A nonexistent task, or a metadata-only task without status, returns a KeyError business failure. queued/running are not terminal states.

## read_task_log

Read logs within a bounded byte window.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_id` | string | Yes | `— (omitted)` | Full Task ID |
| `offset` | integer | No | `-1` | Starting byte offset for log reading; -1 reads the tail; minimum=-1 |
| `limit` | integer | No | `65536` | Maximum number of bytes to read; minimum=1024, maximum=262144 |

The Schema does not prohibit extra fields; this does not mean those fields will be used.

**Request**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo",
    "offset": -1,
    "limit": 65536
  }
}
```

**Response**

answer is TaskLogChunk: content, start_offset, next_offset, file_size, has_more_before, has_more_after, and reset.

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

**Behavior and failure cases**

offset=-1 reads the tail; offset=0 starts at the beginning. limit is measured in bytes, rather than lines. String length after UTF-8 decoding cannot replace next_offset; use the returned next_offset for subsequent reads.

## stream_task

Follow progress and logs until the task stops.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_id` | string | Yes | `— (omitted)` | Full Task ID; minLength=1 |
| `poll_interval` | number | No | `0.5` | Polling interval in seconds; exclusiveMinimum=0 |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**Response**

For an ordinary call, answer is the terminal TaskStatus. SSE emits progress/log events and the final result carries the same status. success is set according to exit_code==0.

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task_type": "base",
    "task_name": "demo",
    "state": "succeeded",
    "config": {
      "task_name": "api-demo",
      "source_tasks": "",
      "x": 1,
      "y": 2,
      "fail": false
    },
    "created_at": "2026-10-02T00:00:00Z",
    "started_at": null,
    "finished_at": null,
    "pid": null,
    "exit_code": 0,
    "error": "",
    "result": {},
    "steps": [],
    "log_path": ""
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

poll_interval defaults to 0.5 seconds. An ordinary HTTP call also waits until a terminal state; all log events are not collected into answer. Use /events for live display.

## get_task_graph

Read the dependency graph containing the selected Task.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_id` | string | Yes | `— (omitted)` | Full Task ID |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**Response**

answer contains root_id, selected_id, nodes, and edges; nodes distinguish missing and provisional.

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

**Behavior and failure cases**

The graph comes from source_tasks in status/metadata and represents recorded relationships; it does not execute a DAG. See the task-lineage documentation for node structures; this example shows only the top-level shape.

## get_task_context

Provide the Agent with task paths, status, and relationship context.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_id` | string | Yes | `— (omitted)` | Full Task ID; minLength=1 |

Only the business fields listed in the table are accepted.

**Request**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**Response**

answer contains task_id, status, metadata_exists, metadata_path, log_path, graph, and relations. relations includes direct_upstream, ancestors, direct_downstream, missing, and provisional.

```json
{
  "answer": {
    "task_id": "base#demo#api-demo",
    "status": {
      "task_id": "base#demo#api-demo",
      "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
      "task_type": "base",
      "task_name": "demo",
      "state": "queued",
      "config": {
        "task_name": "api-demo",
        "source_tasks": "",
        "x": 1,
        "y": 2,
        "fail": false
      },
      "created_at": "2026-10-02T00:00:00Z",
      "started_at": null,
      "finished_at": null,
      "pid": null,
      "exit_code": 0,
      "error": "",
      "result": {},
      "steps": [],
      "log_path": ""
    },
    "metadata_exists": false,
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

**Behavior and failure cases**

metadata_exists indicates whether a node in the graph has published metadata; successful submission alone does not establish that artifacts exist.

## cancel

Request cancellation of an active worker managed by this service.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_id` | string | Yes | `— (omitted)` | Full Task ID |

The Schema does not prohibit extra fields; this does not mean those fields will be used.

**Request**

```json
{
  "arguments": {
    "task_id": "base#demo#api-demo"
  }
}
```

**Response**

answer is a boolean: true means cancellation occurred in this invocation; false means no cancellation occurred.

```json
{
  "answer": false,
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Tasks already in a terminal state, or without a cancellable managed process, return false; success=true and answer=false may occur together. Cancelling a research task does not cancel an Agent turn.

## delete_tasks

Delete terminal or metadata-only Tasks and associated files.

| Parameter | Type | Required | Default | Constraints and meaning |
| --- | --- | --- | --- | --- |
| `task_ids` | array | Yes | `— (omitted)` | List of full Task IDs to delete; minItems=1, uniqueItems=True |

The Schema does not prohibit extra fields; this does not mean those fields will be used.

**Request**

```json
{
  "arguments": {
    "task_ids": [
      "base#demo#api-demo"
    ]
  }
}
```

**Response**

answer is the list of Task IDs actually deleted successfully.

```json
{
  "answer": [
    "base#demo#api-demo"
  ],
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Active tasks, invalid IDs, nonexistent tasks, and managed executions are skipped. Compare the requested and returned lists; success=true does not mean everything was deleted.

## Failure response examples

Schema failures return HTTP 422 before execution, for example when wait_task lacks run_id. Exceptions during Task execution or queries usually return HTTP 200 with success=false. Example of an unknown Task registration name:

```json
{"answer":"ValueError: Unknown Task: missing. Available: demo","success":false,"metadata":{}}
```

The Available list is generated from the actual installed environment. When wait_task returns a failed task status, answer remains TaskStatus with state=failed/cancelled, retaining error and exit_code; do not assume that a failure answer is always a string.

Deletion and cancellation can return a valid request with no changes: delete_tasks may return answer=[], and cancel may return answer=false, alongside success=true. Clients should display the actual number of changes.

## Related documentation

- [Protocol, authentication, and errors](overview.md)
- [Task submission and management](../guides/task-management.md)
- [CLI reference](../reference/cli.md)
- [Event protocol](events.md)

Implementation references: `axonx/config/default.yaml`, `axonx/steps/task/` and `axonx/components/service/http/jobs.py`.
