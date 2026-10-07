---
title: Composite Tasks
description: Combine registered Tasks with synchronous Python steps, explicit inputs, and independent child records.
---

# Composite Tasks

`BaseCompositeTask` is a thin authoring layer over `BaseTask`. A composite is submitted, queried, and cancelled through the existing Task interfaces. Its children run sequentially in the parent's worker through `TaskRunner`, with separate Task IDs, run IDs, status files, metadata, and artifacts. Children share the worker PID and log file; they are not independently supervised workers.

Use ordinary Python to express sequences, loops, and conditions. No Workflow service or configuration language is required. This first version supports local synchronous composition; it does not implement parallel execution, automatic retries, crash-resume, or distributed scheduling.

## Author a composite

This complete example first adds two values, then repeatedly doubles the result using the built-in `demo` Task. Save it as `example_plugin/chain.py` in a plugin package:

```python
from pydantic import Field

from axonx.task import (
    BaseCompositeOutputParams,
    BaseCompositeTask,
    BaseInputParams,
)


class ChainInput(BaseInputParams):
    x: int
    y: int
    doubles: int = Field(default=2, ge=0)


class ChainOutput(BaseCompositeOutputParams):
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
                source_tasks=previous.task_id,
            )
        self.state["total"] = previous.output["result"]

    def build_output_params(self):
        return self.output_cls(**self.composition_output(), total=self.state["total"])
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

`run_task()` must be called while the parent is executing through `TaskRunner`. `task` is an installed registration name. `node_name` defaults to that name and accepts letters, digits, underscores, and hyphens. Repeating a node name records another numbered attempt; a node name cannot switch to a different Task definition.

The returned `ChildTaskResult` provides `task_id`, `run_id`, `success`, `record`, `output_params`, and `output`. `output_params` retains the child's declared Pydantic model; `output` is its JSON-mode dictionary. A construction/validation failure has no Task ID, and an exception before output preparation has no output. Check `success` before consuming results after a continued failure.

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

Stage barriers are ordinary loop boundaries. To preserve a nightly feature/prediction pipeline, run the complete feature loop first, retain its results by time slot, then run the prediction loop with those results. Date, model version, and other business inputs should be resolved once and passed explicitly to the children.

## Records, ownership, and cancellation

The parent writes `composition.json` before executing each child and updates it after completion or failure. It contains a format version, parent `task_id`/`run_id`, and child entries with node name, attempt number, registration name, Task ID when available, run ID, state, exit code, and error. A running entry is not itself a readiness signal; inspect the child's status and data contract when needed.

`BaseCompositeOutputParams` includes `composition_file`, child summaries, and a checksummed `composition` artifact. Use `composition_output()` to include these fields in custom typed output. Fail-fast parents retain the composition file even though successful metadata is not written.

Containment does not create data-lineage edges. Pass `source_tasks` explicitly for actual upstream data dependencies. The runtime owns child instance names; passing `task_name` to `run_task()` is rejected. Child names fit the existing 32-character contract and include a digest of the parent run, node, and attempt. The runtime claims their directories exclusively, preventing accidental replacement of existing child results.

Cancel the **parent** through TaskManager. The shared worker stops, then the manager settles active children, including nested composites, as cancelled. Unexpected worker exits settle them as failed. Already terminal children and replacement/foreign executions remain unchanged. A child is queryable through existing interfaces but cannot be cancelled independently through TaskManager because it has no separately managed worker. For `exec`, cancellation/termination is owned by the calling process; a separate service cannot settle that process's children.

Fixed-name parent reruns retain existing Task replacement semantics: the previous parent directory is replaced, while uniquely named child directories remain. Use distinct parent names when preserving the full composition history matters. Deletion of a parent does not cascade to its children, and deleting a child does not update the parent's record.

Composition does not add resource locking or change cron overlap behavior. Protect shared data writes explicitly; the current Scheduler's `forbid` covers the Job invocation, not the lifetime of a submitted background Task. See [scheduling](scheduling.md).

Source: [composite authoring](../../../axonx/task/composite.py), [composition records](../../../axonx/task/storage/composition.py), [TaskRunner](../../../axonx/task/runtime/runner.py).
