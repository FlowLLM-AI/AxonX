# Task input, output, and persistence contracts

This page defines the basic contracts shared by Task authors, API users, and file consumers. See [Research artifact contracts](research-artifacts.md) for research-specific fields and [Task lifecycle](../concepts/task-lifecycle.md) for execution semantics. Timestamps and run_id values in the following examples are illustrative.

All persisted Task records use the shared protocol header `version=1`, `task_type=TaskType`; readers reject absent or unsupported versions.

## Input and output base classes

BaseInputParams uses `extra="forbid"` and assignment validation. Each Task's input_cls declares business fields on top of the base class.

| Base input field | Type and default             | Constraints                                                                 |
| ---------------- | ---------------------------- | --------------------------------------------------------------------------- |
| task_name        | string or null; default null | 1–32 letters, digits, or hyphens; an empty string is treated as unspecified |
| source_tasks     | string; default empty string | Valid Task IDs separated by ASCII commas; duplicate IDs are rejected        |

`source_tasks` strips whitespace around each item and rejoins them. `source_task(TaskType.X)` requires exactly one upstream task of the specified type; it does not automatically validate that the directory or artifacts exist.

BaseOutputParams uses `extra="forbid"` and `populate_by_name=True`. Its base field is `artifacts: dict[str, dict[str, Any]]`, defaulting to an empty dictionary. output_cls should explicitly declare business extension fields.

```python
from axonx.task.core import BaseInputParams, BaseOutputParams

class AddInput(BaseInputParams):
    x: int
    y: int

class AddOutput(BaseOutputParams):
    result: int
```

`build_output_params()` must return an output_cls instance; returning a plain dict or the wrong type fails. Output is readable only after execution completes and prepare_output runs.

## Composite Task contracts

`axonx.task` exports `BaseCompositeTask`, `ChildTaskResult`, and `ChildTaskError`. The default Task type is `composite`, and the default output model is `BaseOutputParams`. Custom composite outputs extend `BaseOutputParams` with business fields only.

The parent's `metadata.json.children` is the sole containment record. Each entry records `node_name`, positive `attempt`, registered `task`, nullable `task_id`, `run_id`, `state`, `exit_code` (0–255), and `error`. Failed construction attempts have no Task ID. There is no separate composition file or composition artifact; containment is independent of `source_tasks` lineage. See [Composite Tasks](../guides/composite-tasks.md).

## TaskContext

TaskContext is a frozen dataclass attached to a Task, providing runtime-owned values:

| Field             | Type          | Purpose                          |
| ----------------- | ------------- | -------------------------------- |
| workspace_path    | Path          | Resolved workspace root          |
| registration_name | string        | Definition registration name     |
| task_id           | string        | Directory identity               |
| run_id            | string        | Execution identity               |
| created_at        | datetime      | Creation time for this execution |
| logger            | Logger object | Record step execution            |

Plugins should read these values without changing execution identity. `task.task_dir` is `<workspace>/<type>/<task_id>`; `source_task_dir(id)` locates an upstream directory in the same workspace.

## TaskDefinition and TaskHandle

TaskDefinition describes an executable definition with name, source (native/plugin), plugin (nullable), task_type, description, input_schema, and output_schema. description comes from the Task class docstring; missing or whitespace-only docstrings produce an empty string without blocking the Task or catalog.

TaskHandle is the immutable dataclass returned by submit:

```json
{
  "task_id": "base#demo#contract-01",
  "run_id": "a9f248807a0a496abf3738422b379a51",
  "task": "demo"
}
```

The `task` field is the registration name. There is no `task_name` field or address for automatic remote routing. Clients must retain execution-machine information and use task_id + run_id to wait for this execution.

## TaskMetadata

`metadata.json` is the authoritative lifecycle record from acceptance through completion, failure, or cancellation. Status queries return this same schema. The Runner updates one in-memory record and atomically replaces the file; Composite Tasks publish child snapshots through that Runner. After a worker stops, the manager reads its latest record and settles only matching Run IDs and PIDs. Ordinary text logs remain separate.

| Field                                     | Meaning                                                                |
| ----------------------------------------- | ---------------------------------------------------------------------- |
| `task_id`, `run_id`, `task_type`          | Directory identity, current execution identity, and category           |
| `reg_name`                                | Registered Task definition name                                        |
| `input_params`                            | Typed input as JSON, including instance `task_name` and `source_tasks` |
| `output_params`                           | Constructed business output; empty before preparation                  |
| `state`, `exit_code`, `error`             | Current outcome; exit code is 0–255                                    |
| `pid`, `log_path`                         | Owning worker and separate text log                                    |
| `created_at`, `started_at`, `finished_at` | Nullable lifecycle timestamps                                          |
| `steps`                                   | Step names, timestamps, and nullable percentages (0–100)               |
| `children`                                | Child invocation snapshots, including failures before construction     |

Non-finite floating-point values become `null` when persisted. A failed nonzero exit may still have `output_params`; consumers must check `state` before treating output as a successful research artifact. The shared research helper `read_metadata()` requires `state=succeeded` and rejects missing or unsuccessful states; lifecycle inspection uses status queries or `read_task_metadata()` instead. Unknown legacy fields and old status/composition files are not read or migrated.

```json
{
  "task_id": "base#demo#contract-01",
  "run_id": "a9f248807a0a496abf3738422b379a51",
  "task_type": "base",
  "reg_name": "demo",
  "input_params": {
    "task_name": "contract-01",
    "source_tasks": "",
    "x": 1,
    "y": 2,
    "fail": false
  },
  "output_params": {
    "artifacts": {},
    "result": 3,
    "branch": "different",
    "operands": ["x", "y"]
  },
  "children": [],
  "state": "succeeded",
  "pid": 1234,
  "created_at": "2026-01-05T09:00:00+08:00",
  "started_at": "2026-01-05T09:00:01+08:00",
  "finished_at": "2026-01-05T09:00:02+08:00",
  "steps": [
    {
      "name": "finish",
      "started_at": "2026-01-05T09:00:01+08:00",
      "finished_at": "2026-01-05T09:00:02+08:00",
      "percentage": 100
    }
  ],
  "error": "",
  "exit_code": 0,
  "log_path": ".axonx/logs/task.log"
}
```

## Artifact records

```json
{
  "artifacts": {
    "dataset": {
      "path": "data/dataset.parquet",
      "size": 10240,
      "sha256": "<64-digit hexadecimal checksum>"
    }
  }
}
```

The base class only specifies artifacts as a nested mapping. path, size, and sha256 are records generated by standard artifact utilities, which research plugins should use. artifact_path() requires a nonempty path relative to the Task directory that does not escape it.

Do not include the workspace root in artifact path. Consumers combine `<type>/<task_id>/<artifact.path>` and check the producing plugin's expected logical names, such as dataset, model, or daily.

## Workspace reads and events

TaskMetadata requires run_id as the run identity.

Workspace reading rejects invalid JSON, incorrect task_id/type, and unsafe directories, making records appear missing. Tolerant reading isolates bad records; it does not guarantee automatic repair of old data.

events.jsonl is an append-only progress record; ordinary logs are stored at log_path. Writers record progress first, then publish matching status, giving terminal-state consumers a chance to read preceding events. See [Event protocol](../api/events.md) for transport projections and final result rules.

[Jobs and Tasks](../concepts/jobs-and-tasks.md) · [Task API](../api/tasks.md) · [Research artifact contracts](research-artifacts.md)

Source: [Input/output](../../../axonx/task/core/params.py), [Context](../../../axonx/task/core/context.py), [Definitions](../../../axonx/task/catalog/resolver.py), [Handle](../../../axonx/task/contracts/submission.py), [Status](../../../axonx/task/storage/workspace.py), [Metadata](../../../axonx/task/storage/workspace.py).
