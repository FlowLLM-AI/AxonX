# Task input, output, and persistence contracts

This page defines the basic contracts shared by Task authors, API users, and file consumers. See [Research artifact contracts](research-artifacts.md) for research-specific fields and [Task lifecycle](../concepts/task-lifecycle.md) for execution semantics. Timestamps and run_id values in the following examples are illustrative.

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

`axonx.task` exports `BaseCompositeTask`, `BaseCompositeOutputParams`, `ChildTaskResult`, and `ChildTaskError`. The composite's default Task type is `base`; children keep the type and input/output contracts declared by their own definitions.

`BaseCompositeOutputParams` extends `BaseOutputParams` with required `composition_file: str` and `children: list[ChildTaskRecord]` (default empty). `composition_output()` supplies these fields and an `artifacts.composition` record whose relative path is `composition.json`. Custom output models extend this envelope with business fields.

The parent-owned `composition.json` has `version: 1`, `task_id`, `run_id`, and `children`. Each child entry records `node_name`, a positive `attempt`, the registered `task`, nullable `task_id`, `run_id`, `state`, `exit_code` (0–255), and `error`. Entries include failed construction attempts with no Task ID. Containment is independent of `source_tasks` lineage. See [Composite Tasks](../guides/composite-tasks.md) for invocation, failure, and cancellation semantics.

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

## TaskStatus

| Field                                 | Type/default                 | Meaning                                                              |
| ------------------------------------- | ---------------------------- | -------------------------------------------------------------------- |
| task_id                               | string; required             | Must match the directory ID                                          |
| run_id                                | Nonempty string; required    | Current execution identity                                           |
| task_type                             | TaskType; required           | Must match the type in the ID                                        |
| task_name                             | string; default empty string | The current implementation writes the registration name              |
| config                                | object; default {}           | JSON representation of typed input, including the instance task_name |
| state                                 | TaskState; default queued    | Current execution state                                              |
| pid                                   | integer or null              | Process identifier at that time                                      |
| created_at / started_at / finished_at | datetime or null             | Creation, start, and finish times                                    |
| steps                                 | TaskStepStatus[]; default [] | Snapshots of started steps                                           |
| result                                | object; default {}           | Constructed typed output                                             |
| error                                 | string; default empty string | Error description                                                    |
| exit_code                             | integer; default 0           | 0–255                                                                |
| log_path                              | string; default empty string | Separate log file location                                           |

TaskStepStatus contains nonempty name, nullable started_at/finished_at, and nullable percentage (0–100). The percentage describes the current step, rather than progress of the entire research task.

A simplified complete example of a successful status:

```json
{
  "task_id": "base#demo#contract-01",
  "run_id": "a9f248807a0a496abf3738422b379a51",
  "task_type": "base",
  "task_name": "demo",
  "config": {
    "task_name": "contract-01",
    "source_tasks": "",
    "x": 1,
    "y": 2,
    "fail": false
  },
  "state": "succeeded",
  "pid": 12345,
  "created_at": "2026-01-05T09:00:00+08:00",
  "started_at": "2026-01-05T01:00:00Z",
  "finished_at": "2026-01-05T01:00:01Z",
  "steps": [
    {
      "name": "finish",
      "started_at": "2026-01-05T01:00:00Z",
      "finished_at": "2026-01-05T01:00:01Z",
      "percentage": 100
    }
  ],
  "result": {
    "artifacts": {},
    "result": 3,
    "branch": "different",
    "operands": ["x", "y"]
  },
  "error": "",
  "exit_code": 0,
  "log_path": ""
}
```

steps shows only the final step; the actual demo includes more steps. The log value is empty solely to avoid specifying a deployment path; the logging system supplies the actual value.

The key differences on failure are shown below; this is not a separate complete TaskStatus:

```json
{
  "state": "failed",
  "result": {},
  "error": "RuntimeError: Demo failure requested",
  "exit_code": 1
}
```

A custom nonzero exit code also produces failed, but result may already exist; failure does not necessarily mean output was never constructed. The manager records cancellation as cancelled, usually with exit code 130.

## TaskMetadata

The metadata top level strictly represents successful tasks' inputs and outputs:

```json
{
  "task_id": "base#demo#contract-01",
  "reg_name": "demo",
  "created_at": "2026-01-05T09:00:00+08:00",
  "task_type": "base",
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
  }
}
```

metadata has no top-level run_id, state, result, or error. TaskStatus.result corresponds to metadata.output_params; the task identity's registration name is in metadata.reg_name.

A successful execution first constructs output and determines the exit code, then writes metadata and publishes successful status. When metadata is written, nonfinite floating-point values are recursively converted to null for JSON consumers.

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

## Compatible reads and events

TaskStatus reading supports the historical execution_id field as a validation alias for run_id. New writes still use run_id; do not write both identity fields or treat execution_id as a new API field.

Workspace reading rejects invalid JSON, incorrect task_id/type, and unsafe directories, making records appear missing. Tolerant reading isolates bad records; it does not guarantee automatic repair of old data.

events.jsonl is an append-only progress record; ordinary logs are stored at log_path. Writers record progress first, then publish matching status, giving terminal-state consumers a chance to read preceding events. See [Event protocol](../api/events.md) for transport projections and final result rules.

[Jobs and Tasks](../concepts/jobs-and-tasks.md) · [Task API](../api/tasks.md) · [Research artifact contracts](research-artifacts.md)

Source: [Input/output](../../../axonx/task/core/params.py), [Context](../../../axonx/task/core/context.py), [Definitions](../../../axonx/task/catalog/resolver.py), [Handle](../../../axonx/task/contracts/submission.py), [Status](../../../axonx/task/storage/workspace.py), [Metadata](../../../axonx/task/storage/metadata.py).
