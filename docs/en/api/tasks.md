# Task Execution and Observation API

Execution goes through the native CLI or the service-owned `cli` command Job; observation reads persisted Task records.

Use the [HTTP/MCP protocol](overview.md) and discover schemas with `axonx help --job NAME`. Replace example Task/session IDs with actual values.

## Endpoint list

| Job                  | Purpose                                                                                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cli`                | Run an AxonX CLI command in a child process on this service machine. Paths belong to this machine; start and nested remote forwarding are not supported. |
| `list_task_defs`     | List registered Tasks in this service's Python environment; schemas can be omitted for lightweight discovery.                                            |
| `get_task_def`       | Get one registered Task's description and input/output schemas from this service's Python environment.                                                   |
| `wait_task`          | Wait for the current Task to finish; refuse a restart while waiting.                                                                                     |
| `list_task_ids`      | List Task IDs with valid metadata.json records in the index.                                                                                             |
| `list_task_statuses` | List Task status snapshots or lightweight summaries.                                                                                                     |
| `status`             | Get one task status.                                                                                                                                     |
| `read_task_log`      | Read a bounded byte range from one Task log.                                                                                                             |
| `stream_task`        | Follow one Task, streaming its progress and log until it stops.                                                                                          |
| `get_task_graph`     | Return the dependency graph containing any workspace Task.                                                                                               |
| `get_task_context`   | Return full Task metadata, its path, and input-dependency context for an Agent.                                                                          |

## cli

Run an AxonX CLI command in a child process on this service machine. Paths belong to this machine; start and nested remote forwarding are not supported.

| Argument | Type    | Required | Default / constraints |
| -------- | ------- | -------- | --------------------- |
| `argv`   | `array` | yes      | `{"minItems":1}`      |

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

Runs argv without a shell in the service workspace. The configured command/interpreter owns a child process group. Returns stdout, stderr, exit_code and per-channel truncation flags (each retained output is limited to a 1 MiB prefix); streamed log events identify stdout/stderr. The default cli Job continues after client disconnection, drains both output pipes and discards unobserved events. Explicit Task kill or service shutdown terminates execution. Nested forwarding and service startup are rejected. Use argv `["plugin", "install", absolute_location]` for an already uploaded wheel.

## list_task_defs

List registered Tasks in this service's Python environment; schemas can be omitted for lightweight discovery.

| Argument          | Type      | Required | Default / constraints |
| ----------------- | --------- | -------- | --------------------- |
| `include_schemas` | `boolean` | no       | `{"default":true}`    |

```json
{
  "arguments": {
    "include_schemas": false
  }
}
```

Reads the persistent service catalog. `include_schemas=false` omits schemas, but still resolves registered classes. A new plugin installation does not rebuild this startup snapshot.

## get_task_def

Get one registered Task's description and input/output schemas from this service's Python environment.

| Argument | Type     | Required | Default / constraints |
| -------- | -------- | -------- | --------------------- |
| `task`   | `string` | yes      | `{"minLength":1}`     |

```json
{
  "arguments": {
    "task": "demo"
  }
}
```

Returns name, source, plugin, task_type, description, input_schema and output_schema for one registration.

## wait_task

Wait for the current Task to finish; refuse a restart while waiting.

| Argument        | Type     | Required | Default / constraints                          |
| --------------- | -------- | -------- | ---------------------------------------------- |
| `task_id`       | `string` | yes      | `{"minLength":1}`                              |
| `poll_interval` | `number` | no       | `{"exclusiveMinimum":0,"default":1}`           |
| `detail`        | `string` | no       | `{"enum":["summary","full"],"default":"full"}` |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check",
    "poll_interval": 1,
    "detail": "full"
  }
}
```

Captures the current started_at and rejects replacement while waiting. Returns a summary or complete metadata; success is true only for succeeded. There is no business timeout input; allow a sufficient client timeout.

## list_task_ids

List Task IDs with valid metadata.json records in the index.

No business arguments.

```json
{
  "arguments": {}
}
```

## list_task_statuses

List Task status snapshots or lightweight summaries.

| Argument    | Type     | Required | Default / constraints                                   |
| ----------- | -------- | -------- | ------------------------------------------------------- |
| `detail`    | `string` | no       | `{"enum":["summary","full"],"default":"summary"}`       |
| `task_type` | `string` | no       | `—`                                                     |
| `state`     | `string` | no       | `{"enum":["running","succeeded","failed","cancelled"]}` |

```json
{
  "arguments": {
    "detail": "summary"
  }
}
```

Both detail modes return a list sorted by creation time, newest first, with Task ID as the tie-breaker. Filters apply before full records are copied. `summary` contains TaskStatus fields plus `display_name`, `is_replica` and optional `step_progress` (`current`, `total`, `name`, `percentage`), omitting inputs, outputs, steps and child arrays. Summary errors are limited to 1000 characters; display and step names to 256. Lists use the periodically refreshed index (default 5 seconds); `status` and `wait_task` read the selected metadata directly.

## status

Get one task status.

| Argument  | Type     | Required | Default / constraints                          |
| --------- | -------- | -------- | ---------------------------------------------- |
| `detail`  | `string` | no       | `{"enum":["summary","full"],"default":"full"}` |
| `task_id` | `string` | yes      | `—`                                            |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check",
    "detail": "full"
  }
}
```

Reads current metadata or a summary. Queries do not repair stale running records. Compare started_at with the execution being observed.

## read_task_log

Read a bounded byte range from one Task log.

| Argument     | Type      | Required | Default / constraints                           |
| ------------ | --------- | -------- | ----------------------------------------------- |
| `task_id`    | `string`  | yes      | `—`                                             |
| `started_at` | `string`  | no       | `{"format":"date-time"}`                        |
| `offset`     | `integer` | no       | `{"minimum":-1,"default":-1}`                   |
| `limit`      | `integer` | no       | `{"minimum":1,"maximum":262144,"default":8192}` |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check",
    "offset": -1,
    "limit": 8192
  }
}
```

Returns content, start_offset, next_offset, file_size, has_more_before, has_more_after and reset; also emits a log event. The optional started_at rejects a replacement before reading. Offsets are byte positions.

## stream_task

Follow one Task, streaming its progress and log until it stops.

| Argument        | Type     | Required | Default / constraints                  |
| --------------- | -------- | -------- | -------------------------------------- |
| `task_id`       | `string` | yes      | `{"minLength":1}`                      |
| `poll_interval` | `number` | no       | `{"exclusiveMinimum":0,"default":0.5}` |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check"
  }
}
```

Streams progress/logs and ends with current metadata in the terminal result. An observed replacement is an error. A subscription does not launch the Task.

## get_task_graph

Return the dependency graph containing any workspace Task.

| Argument  | Type     | Required | Default / constraints |
| --------- | -------- | -------- | --------------------- |
| `task_id` | `string` | yes      | `—`                   |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check"
  }
}
```

Returns `root_id`, `selected_id`, `nodes` and directed `edges` (`from` → `to`) for the connected input-dependency component. Edges come only from `input_params.upstream_task_ids`; parent/child invocations remain in Task metadata. `missing` marks an unavailable referenced record; `provisional` marks an existing record whose state is not `succeeded`. This query does not execute dependencies.

## get_task_context

Return full Task metadata, its path, and input-dependency context for an Agent.

| Argument  | Type     | Required | Default / constraints |
| --------- | -------- | -------- | --------------------- |
| `task_id` | `string` | yes      | `{"minLength":1}`     |

```json
{
  "arguments": {
    "task_id": "base#demo#api-check"
  }
}
```

Returns `task_id`, full `status` (TaskMetadata), workspace-relative `metadata_path`, `graph` and `relations`. Relations contain `direct_upstream`, `all_upstream`, `direct_downstream`, `missing` and `provisional`. The selected record is read fresh; other graph records come from the current index snapshot. Inputs, outputs and child records are included in full, so this is not a byte-limited context summary.

## Results and lifecycle

TaskMetadata has task_id, task_type, reg_name, parent_task_id, report_kind, state, process identity, started_at, input/output parameters, steps, children and optional display replica metadata. Produced Task states are running/succeeded/failed. The state filter schema also advertises a cancellation value that the current Task model does not produce. Summaries omit large business inputs/outputs.

For termination call `cli` with `["kill", "--task-id", "ID"]`. General directory cleanup uses `delete_entries` after execution stops; there is no dedicated Task deletion Job. See [Task contracts](../reference/task-contracts.md).

Source: [Default Job contracts](../../../axonx/app/config/default.yaml) · [Job protocol](overview.md)
