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

TaskDefinition describes an executable definition with name, source (native/plugin), plugin (nullable), task_type, description, input_schema, and output_schema. description comes from the Task class docstring; missing or whitespace-only docstrings produce an empty string without blocking the Task or catalog.

```json
{
  "task_id": "base#demo#contract-01",
  "run_id": "a9f248807a0a496abf3738422b379a51",
  "task": "demo"
}
```

The `task` field is the registration name. There is no `task_name` field or address for automatic remote routing. Clients must retain execution-machine information and use task_id + run_id to wait for this execution.

## TaskMetadata

metadata.json is the lifecycle record published by the Task, containing parameters, progress, children and output. The Runner replaces it atomically; the observing service never writes lifecycle state. Text logs are stored separately.

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
      "revision": "<size>:<mtime_ns>"
    }
  }
}
```

The base class only specifies artifacts as a nested mapping. path, size, and revision are records generated by standard artifact utilities, which research plugins should use. artifact_path() requires a nonempty path relative to the Task directory that does not escape it.

Do not include the workspace root in artifact path. Consumers combine `<type>/<task_id>/<artifact.path>` and check the producing plugin's expected logical names, such as dataset, model, or daily.

`axonx.task.artifact.ArtifactRecord` owns portable relative path, byte size and SHA256 validation. The existing `ArtifactRecord` import is an alias of that record. Public output mappings retain their JSON shape. `PortfolioSettings` in `axonx.task.builtins.stock` owns common portfolio fields and conversion to the execution engine; plugins override business defaults and selection rules.

Online publication keeps `persistent/online/manifest.json` as a complete, self-contained v1 history. New frozen `commits/<commit_id>/history.json` files use `kind=online_history_node`: at most 16 commits plus a size/revision-checked Task-relative reference to the preceding completed group. Use `read_online_history()` to read either representation. Existing full snapshots remain readable and can precede new nodes; no old records are rewritten. Copying a frozen node requires its referenced predecessor files, which Task synchronization includes automatically. `pin_online_history()` exports a complete v1 history and all referenced artifacts for independent consumption.

Frozen history metadata grows linearly for new revisions, while the current manifest remains a full-history document. Portfolio Parquet revisions remain complete audit reports. Consumer pinning makes an isolated copy of each distinct artifact reference and shares only consumer-owned copies, so in-place upstream writes cannot change a pinned input. Treat pinned inputs as immutable. `TaskExecution.output` reads the final status output directly rather than retaining a second serialized result.

## Workspace reads and events

TaskMetadata requires run_id as the run identity.

Workspace reading rejects invalid JSON, incorrect task_id/type, and unsafe directories, making records appear missing. Tolerant reading isolates bad records; it does not guarantee automatic repair of old data.

events.jsonl is an append-only progress record; ordinary logs are stored at log_path. Writers record progress first, then publish matching status, giving terminal-state consumers a chance to read preceding events. See [Event protocol](../api/events.md) for transport projections and final result rules.

[Jobs and Tasks](../concepts/jobs-and-tasks.md) · [Task API](../api/tasks.md) · [Research artifact contracts](research-artifacts.md)

Source: [Input/output](../../../axonx/task/core/params.py), [Context](../../../axonx/task/core/context.py), [Definitions](../../../axonx/task/catalog/resolver.py), [Status](../../../axonx/task/storage/workspace.py), [Metadata](../../../axonx/task/storage/workspace.py).

## Display replicas

`TaskMetadata.replica` is null for source runs. A synchronized result has a display manifest containing `purpose`, `source_revision`, `policy_revision`, `files`, `omitted`, and `source_log_path`. Each file records actual size/revision and optional sampling rows/dates. Source outputs and metrics remain original; display consumers use the actual file manifest. Research input consumers reject replicas.

## Concurrent step progress

`BaseTask.report_progress(percentage)` updates the executing step. `report_progress(name="download", state="running", completed=10, total=100, unit="requests")` updates a named substep in the same `metadata.steps` list. Each substep has a `parent` identifying the executing step. `TaskStepStatus` is shared by metadata and `ProgressEvent` (`kind=progress`); there is no separate activity object, event or storage field. Optional fields cover labels/groups, state/phase, counts, schedules/deadlines, metrics, committed file paths and errors. Request completion and usable coverage are separate measurements.

The Runner serializes progress updates and metadata publication. Named counter updates are throttled to once per second per substep; state/phase changes and terminal updates publish immediately. Final snapshots retain all counts. Stop and join background producers before their executing step returns. Failure/cancellation and worker-exit cleanup settle unfinished progress while preserving completed work. Window results remain business outputs; progress never publishes business artifacts or online commits.

`children` is the sole lifecycle record for child invocations. Planned models come from validated task inputs; the UI derives their execution state from child records and their internal phases from child steps. A named child directory contains the latest invocation; earlier attempts remain in the parent's records, and display synchronization captures only the latest invocation per directory. It rejects an unexpected replacement Run rather than substituting it.

Tasks declare `report_kind = "online_pipeline"` or `"compare_pipeline"` to select their Studio report; operational indexes use TaskCategory. Online plans group models by signal time; nightly comparison plans list models and show shared preparation followed by per-model stages. Both use `metadata.steps` for progress and `metadata.children` for exact Run references, including nested composites. `run_task(..., task_name="model-1445")` names a child explicitly and defaults its node name to `<task_name>-<registration>`; omitting `task_name` inherits the parent name and defaults the node name to the registration. Lifecycle, source inheritance and cleanup are framework-owned. Activity metadata/events and the separate live index response are removed without fallback readers; regenerate records written with those unpublished contracts and upgrade plugins, source services, receivers and Studio together.

Display replicas carry `replica.snapshot` (source, root Task/Run, capture time and revision) and `replica.log` (path and original byte range) when synchronized as a group. They retain source state, clear the PID and remain read-only. See [Display sync](../guides/task-sync.md).

Task classes may declare `category: TaskCategory | None` (`data_update`, `online_prediction`, `comparison`) independently of `task_type` and `report_kind`. Definitions, queued records, persisted metadata and status summaries expose it. In-process composite children also persist `parent_run_id` so operational indexes can omit nested runs without losing their own category. Missing category/parent fields default to null; old records are not classified by Task name.

## Business clocks and event replay

`BaseTask(..., clock=...)` accepts an optional `WindowClock`; composite children inherit the same object. The existing `axonx.task.contracts.WindowClock` import remains valid. The clock controls business windows and deadline budgets; task identity, lifecycle timestamps, logs and runtime performance measurements remain based on real time.

`axonx.task.clock.ReplayClock(start_at)` is a single-driver virtual clock. Only explicit sleeps or `advance_to()` advance time, so computation pauses simulated time. Times must be timezone-aware and cannot move backwards. Workers may read the clock, but only the creating thread may advance it. Threaded plugins must use an event driver or coordinate their waits explicitly; replacing a wall clock alone does not accelerate `Event.wait` or `Condition.wait`.

`axonx.task.replay` provides `ReplaySource`, `ReplayStream` and `ReplayCursor`. `ReplayStream.create(directory, events, context=..., attributes=...)` copies payloads into a new directory and publishes `stream.json`; existing datasets are not overwritten. Each event has a key, timezone-aware `available_at`, file records (relative path, size, SHA256) and plugin attributes. Context files pin run-level inputs. Opening a stream validates ordering, paths and every file revision. Transfer the whole directory, not only its manifest.

`ReplayCursor.wait(deadline, consume, ready)` advances to event availability, consumes ordered events synchronously and stops when `ready()` is true. Events at or after the deadline are not delivered; an exhausted stream advances to the deadline and returns false. Plugins own schemas, market calendars, validation and publication, as well as missing-input policy and isolated outputs. This contract does not synthesize historical responses or permit fallback network access. Plugins must label reconstructed window snapshots separately from original request recordings and record their remaining external dependencies.

## Migration to AxonX 0.2.1

The 0.2.1 release replaces the previous Task and Studio wire contracts. Update the
framework, Studio and consuming plugins together. Axon and Axon2 require
`axonx>=0.2.1`; bundled Qlib plugins require their separately versioned 0.2 peers. Regenerate previous
Task outputs rather than mixing old records with the new schema. These source
changes do not publish packages; install the coordinated source checkouts until
the matching releases are available.

Training member counts are read from the registered model manifest, including
multi-member collections; replicas omitting it show an unavailable count.
Research and comparison lists retain only summaries and load selected details.
