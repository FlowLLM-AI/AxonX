# Task Contracts

## Input and output base classes

Import `BaseTask` from `axonx.task.core.base` and parameters from `axonx.task.models.params`. `BaseInputParams` contains optional `task_name` and `upstream_task_ids: list[str]` (default empty). Names contain 1–32 letters, digits or hyphens. Upstream IDs must be canonical, unique and not the current Task ID. `BaseOutputParams` contains an artifact registry.

Subclasses declare `input_cls`, `output_cls`, `task_type`, optional `report_kind`, synchronous `build_task_steps()` and typed `build_output_params()`. The executor owns metadata/progress and invokes `close()` before final output construction. `publish_output()` validates and persists a partial snapshot; `report_progress()` works only during execution.

## Child Task contracts

Every BaseTask offers `run_task(reg_name, *, node_name=None, on_error="stop", task_name=None, **inputs)`. It returns `ChildTaskResult` with record, success, child_task_id, optional typed output_params and JSON output. Failed construction may have no child ID or output. Accessing unavailable output raises.

Children inherit the parent's name unless overridden and run in the same process. Child records contain node_name, attempt, reg_name, child_task_id, started_at, state, exit_code and error. A failed child with on_error=continue does not automatically make its parent successful. Parent/child calls and upstream dependencies are independent. There is no separate composite Task type.

## TaskContext

The immutable dataclass contains workspace_path, registration_name, task_id, created_at, timezone, optional parent_task_id and execution_target. It does not expose application clients or components.

## Task definitions

`TaskInfo` contains name, source, plugin, task_type and description. `TaskDefinition` adds input_schema and output_schema. Definitions belong to a catalog snapshot; they are not execution handles. CLI exec returns business output and a process exit code.

## TaskMetadata

The complete document combines protocol version/task type with current identity, process ownership and business results:

| Fields                              | Meaning                                         |
| ----------------------------------- | ----------------------------------------------- |
| task_id, reg_name                   | Directory and registration identity             |
| started_at                          | Current execution identity; changes on rerun    |
| state, exit_code, error             | running/succeeded/failed and outcome            |
| machine_id, pid, process_started_at | Verified process identity                       |
| execution_target, workspace_dir     | Optional source-side remote routing information |
| parent_task_id, children            | Invocation relationships                        |
| created_at, finished_at, log_path   | Timing and log location                         |
| input_params, output_params         | Validated business data                         |
| steps                               | Step snapshots                                  |
| replica                             | Optional display-replica metadata               |

Same-name execution overwrites the current record and outputs, retaining persistent/. Callers coordinate writes. Observations do not settle stale records. `wait_task` captures started_at and refuses a replacement during the wait.

## Execute directly in Python

```python
from pathlib import Path
from axonx.task.builtins.demo import DemoTask
from axonx.task.runtime.executor import TaskExecutor

metadata = TaskExecutor().execute(DemoTask(
    {"task_name": "python-check", "x": 1, "y": 2},
    workspace_path=Path(".axonx"),
    reg_name="demo",
))
assert metadata.exit_code == 0
print(metadata.task_id, metadata.started_at, metadata.output_params)
```

Supply a Task resolver to TaskExecutor when executing children. The CLI constructs a catalog from installed plugins and supplies its resolve method.

Child `node_name` identifies a logical invocation independently of its physical Task directory. Keep the model name at its start when publishing model-specific views, and retain the default registration name for shared calls. Progress uses the existing step `name` and `group`; descendants use recorded child Task IDs and start times.

## Artifact records

File records contain relative path, size and revision; paths must remain inside the Task directory. Shared models live in `models.artifacts`, research results in `models.reports`. Use `storage.inputs` to validate and pin upstream artifacts. Atomic metadata publication is not protection against concurrent directory writers.

## Workspace reads and events

`task_index` provides observations. ProgressEvent extends step status, LogEvent extends bounded byte-log chunks; Job events additionally include artifact, agent_message and result. See [Events](../api/events.md).

## Display replicas

Replica metadata identifies source/policy revisions, sampled or omitted files and optional selected workflow snapshots. TaskSnapshot uses source_id, root_task_id, root_started_at, captured_at, ordered revision, when and model_names. Replicas cannot execute or serve as mutable research sources.

## Business clocks and event replay

BaseWindowTask and BaseInferenceTask live in `core.windows`; WindowClock/DeadlineBudget in `core.clock`; ReplayClock in `runtime.replay`. Lifecycle timing remains real. Window business outcomes are independent of Task state. Verify/freeze online history before replay or reporting; see [Research artifacts](research-artifacts.md).

Sources: [authoring](../../../axonx/task/core/base.py), [models](../../../axonx/task/models/lifecycle.py), [executor](../../../axonx/task/runtime/executor.py).
