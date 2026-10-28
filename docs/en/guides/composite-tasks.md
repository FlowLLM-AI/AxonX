# Composing Tasks

Any BaseTask can synchronously call registered children. Conditions, loops and stage barriers belong to the parent Task; no special composite base or Task type is required.

## Author a parent Task

```python
from axonx.task.core.base import BaseTask
from axonx.task.models.params import BaseOutputParams

class ChainOutput(BaseOutputParams):
    total: int

class DemoChainTask(BaseTask):
    """Run two registered additions in one execution process."""
    output_cls = ChainOutput

    def build_task_steps(self):
        yield self.first
        yield self.second

    def first(self):
        result = self.run_task("demo", node_name="first", task_name="first", x=1, y=2)
        self.state["first"] = result.output["result"]

    def second(self):
        result = self.run_task("demo", node_name="second", task_name="second",
                               x=self.state["first"], y=4)
        self.state["total"] = result.output["result"]

    def build_output_params(self):
        return ChainOutput(total=self.state["total"])
```

Register `demo_chain: example_plugin.chain:DemoChainTask` in plugin.yaml, then execute `axonx exec --task demo_chain --task-name experiment`. The result is 7. Children share the parent's process and workspace. This example gives each child an explicit instance; production pipelines should derive child names from the parent when they need isolated experiment outputs.

## Failures and stage barriers

`run_task` returns only after the child finishes. Read result.success, child_task_id, record and output. Default on_error=stop raises ChildTaskError. With continue, the failed record remains and later work may run, but the default parent exit policy still reports failure. Override exit_code only for explicitly handled business outcomes.

Upstream input dependencies must be passed explicitly as upstream_task_ids. Parent/child containment does not create these edges. node_name labels a call and attempt; task_name selects the directory. Repeated calls to one registration/name replace previous current output; consume or pin artifacts first.

## Records, ownership and termination

The parent metadata.children contains call snapshots including construction failures, which may have no child ID. A child has its own Task metadata, but shares process ownership. `kill` resolves a running child to its root owner and terminates the execution process and descendants. It cannot independently stop an in-process child while keeping the parent executing.

Use different parent/child instances for independent experiments and coordinate fixed-name pipelines yourself. Startup/explicit kill reconcile confirmed dead local records; queries remain read-only.

[Task contracts](../reference/task-contracts.md) · [Lifecycle](../concepts/task-lifecycle.md)
