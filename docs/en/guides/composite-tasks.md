---
title: Composite Tasks
description: Combine registered Tasks with synchronous Python steps, explicit inputs, and independent child records.
---

# Composite Tasks

`BaseCompositeTask` is a thin authoring layer over `BaseTask`. A composite is submitted, queried, and cancelled through the existing Task interfaces. Its children run sequentially in the parent's worker through `TaskRunner`, with a separate Run ID for each invocation. Each installed registration defaults to the parent’s resolved `task_name` for its Task ID, unified metadata, and artifact directory. Repeated calls of the same registration replace that directory’s terminal outputs. Children share the worker PID but have separate Run log files; a parent's log also includes its nested children. They are not independently supervised workers. A completed Task's stream drains a bounded log snapshot and ends even if a legacy shared process log keeps growing. Run logs follow the shared 7-day retention policy; active Run logs are protected from cleanup.

Use ordinary Python to express sequences, loops, and conditions. No Workflow service or configuration language is required. This first version supports local synchronous composition; it does not implement parallel execution, automatic retries, crash-resume, or distributed scheduling.

Same-name reruns clear run-owned files, including metadata.json and events.jsonl, while retaining the reserved `persistent/` directory. Use `self.persistent_dir` for cumulative business data; plugins own its schema, updates and locking. Run IDs and lifecycle records still describe only the current execution. Explicit Task deletion removes persistent data too; display synchronization atomically replaces the target Task directory with selected outputs. `persistent/` must be a regular directory, not a symlink.

## Author a composite

This complete example first adds two values, then repeatedly doubles the result using the built-in `demo` Task. Save it as `example_plugin/chain.py` in a plugin package:

```python
from pydantic import Field

from axonx.task import (
    BaseOutputParams,
    BaseCompositeTask,
    BaseInputParams,
)


class ChainInput(BaseInputParams):
    x: int
    y: int
    doubles: int = Field(default=2, ge=0)


class ChainOutput(BaseOutputParams):
    total: int


class DemoChainTask(BaseCompositeTask):
    """Add two values, then double the sum a configurable number of times."""

    input_cls = ChainInput
    output_cls = ChainOutput

    def build_task_steps(self):
        yield self.run_chain

    def run_chain(self):
        previous = self.run_task(
            "demo", node_name="sum", x=self.input_params.x, y=self.input_params.y
        )
        for index in range(self.input_params.doubles):
            total = previous.output["result"]
            previous = self.run_task(
                "demo",
                node_name=f"double-{index}",
                x=total,
                y=total,
            )
        self.state["total"] = previous.output["result"]

    def build_output_params(self):
        return self.output_cls(total=self.state["total"])
```

Declare the Task in the plugin manifest:

```yaml
tasks:
  demo_chain: example_plugin.chain:DemoChainTask
```

Follow [plugin development](../dev_guide.md) to package/install the plugin, then restart the executing service. The following commands assume that `demo_chain` has been installed in the execution environment:

```bash
# Run locally; total is 20
axonx exec --task demo_chain --x 2 --y 3 --doubles 2

# Or submit to the running service, then wait/cancel using the parent's handle
axonx submit --task demo_chain --x 2 --y 3 --doubles 2
```

`run_task()` must be called while the parent is executing through `TaskRunner`. `task` is an installed registration name. `node_name` defaults to that name and accepts letters, digits, underscores, and hyphens. Repeating a node name records another numbered attempt; a node name cannot switch to a different Task definition. Node names and attempt numbers label invocation records and do not affect Task IDs or directories.

The returned `ChildTaskResult` provides `task_id`, `run_id`, `success`, `record`, `output_params`, and `output`. `output_params` retains the child's declared Pydantic model; `output` is its JSON-mode dictionary. A construction/validation failure has no Task ID, and an exception before output preparation has no output. Check `success` before consuming results after a continued failure.

`children` and each result's `record` are defensive snapshots. Changing them does not alter the parent's recorded state. `task`, `node_name`, `on_error`, and `task_name` are reserved by `run_task()`; choose different names for child business input fields.

## Failures and stage barriers

The default `on_error="stop"` raises `ChildTaskError` when a child raises an exception or returns a nonzero exit code. The exception retains its `result`; later work does not run.

Use `on_error="continue"` for batches that should attempt every child:

```python
for dataset in datasets:
    result = self.run_task(
        "download_dataset",
        node_name=dataset,
        on_error="continue",
        dataset=dataset,
    )
    if not result.success:
        self.logger.warning(result.record.error)
```

Here `download_dataset` represents a plugin Task with a matching input schema. Continued failures are recorded and the parent still finishes as failed. Validation and lookup failures also follow this policy. `KeyboardInterrupt` and `SystemExit` always propagate. Repeated calls do not implement automatic retries or erase earlier failures. Preserve the inherited `exit_code()` when extending a composite so this aggregation remains in effect.

Invalid runtime options, such as an unsupported `on_error` or conflicting node definition, raise `ValueError` before a child attempt is recorded. If composition preparation fails before Runner handoff, the runtime closes the child’s resources and records the failed invocation; no child status directory is created. The Runner owns resources from entry: directory checks and initial status publication failures also close resources. After directory preparation, it persists failure status when storage permits; rejected existing runs remain untouched. Continuation requires being able to persist the failure records; persistent storage errors can stop the parent.

For a file-backed feature/prediction batch, run the feature and its prediction inside the same time-slot loop, consuming the feature artifacts before the next feature call replaces them. Keeping a `ChildTaskResult` retains its typed output snapshot, not a copy of its files. For independent per-slot artifacts, execute separate parent instances with distinct `task_name` values. Date, model version, and other business inputs should be resolved once and passed explicitly to the children.

## Records, ownership, and cancellation

The Runner writes `metadata.json` throughout execution. The parent updates its `children` list before each child starts and after completion or failure. Each entry contains node name, attempt, registration name, nullable Task ID, Run ID, state, exit code, and error. A running entry is not itself a readiness signal; inspect the child’s state and artifact contract.

The default composite output is `BaseOutputParams`. Custom outputs extend it with business fields and return them normally; child records are stored only in top-level `metadata.json.children`. Failed and cancelled parents retain the same record, including fail-fast failures before business output is built.

Containment does not create data-lineage edges. Pass `source_tasks` explicitly for actual upstream data dependencies between different Task IDs. Every child, including nested composites, inherits the parent’s resolved `task_name` by default; pass `task_name` to `run_task()` for an explicitly named child instance. The runtime adds no hash, node name, or attempt number to the name. Repeated calls of the same registration use the same Task ID and replace terminal outputs through `TaskRunner`; active and unrecognized directories are rejected. Each invocation gets a new Run ID. A Task cannot use its own Task ID as an upstream source; construction rejects this before either submission or execution can replace any files. Invocation records retain states and errors, while old Run status and artifacts become unavailable after replacement. Parents with the same name share child directories even when their registrations differ. Shared fixed-name pipelines must serialize execution. Replacement does not preserve old Runs or provide failure rollback.

Cancel the **parent** through TaskManager. The shared worker stops, then the manager settles active children, including nested composites, as cancelled. Unexpected worker exits settle them as failed. Already terminal children and replacement/foreign executions remain unchanged. A child is queryable through existing interfaces but cannot be cancelled independently through TaskManager because it has no separately managed worker. For `exec`, cancellation/termination is owned by the calling process; a separate service cannot settle that process's children.

Settlement reads only valid regular metadata matching the parent and child Run IDs. Missing, malformed, stale, symlink, and non-regular records are ignored. Transient I/O errors propagate to the worker-exit monitor for retry; settlement never replaces a foreign Run.

Inspect a submitted run on the same execution target:

```bash
axonx status --task-id '<parent Task ID>'
axonx preview_file --path '<parent Task type>/<parent Task ID>/metadata.json'
axonx status --task-id '<child Task ID from metadata.json>'
axonx cancel --run-id '<parent run_id>'
```

Replace the placeholders with the parent handle and child IDs from `metadata.json.children`. Pure composites default to Task type `composite`, with directories such as `composite/composite#demo_chain#<name>/`; subclasses can use specialized types. Parent steps do not contain child step progress; query each child’s status or stream for that detail.

Fixed-name parent reruns replace the previous parent directory. Child outputs are replaced in the same named directories when their stages execute; children skipped by the new run remain on disk but are absent from its composition. Existing child directories and parents previously stored under `base` are not migrated automatically. Use distinct parent names when preserving the full composition history matters. Deletion of a parent does not cascade to its children, and deleting a child does not update the parent's record.

Composition does not add resource locking or change cron overlap behavior. Protect shared data writes explicitly; the current Scheduler's `forbid` covers the Job invocation, not the lifetime of a submitted background Task. See [scheduling](scheduling.md).

Source: [composite authoring](../../../axonx/task/composite.py), [composition records](../../../axonx/task/storage/composition.py), [TaskRunner](../../../axonx/task/runtime/runner.py).

Children inherit the parent task_name by default. Use `run_task("predict", task_name="model-1445", ...)` for an explicitly named model instance. Node names identify invocation records and do not replace instance names.
