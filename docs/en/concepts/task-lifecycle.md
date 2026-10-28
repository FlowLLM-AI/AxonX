# Task Lifecycle

![Current Task lifecycle](../../figures/concepts/lifecycle.svg)

## Names and execution identity

`task_type`, registration and `task_name` form `type#registration#instance`. The current execution is identified by metadata `started_at`. Runtime ownership uses `machine_id`, `pid`, `process_started_at`, optional reachable `execution_target`, and source `workspace_dir`.

## State meanings

Task states are `running`, `succeeded`, `failed`. A successful result has exit code 0. Process termination and exceptions lead to failure; individual step states also include pending, waiting, done, missed and skipped. A business window can be incomplete without the entire Task failing.

## Step progress

The executor runs synchronous callables from `build_task_steps()`, records their progress and timings, and closes resources before building final output. `report_progress()` supports named substeps; stop background producers before lifecycle completion. `publish_output()` persists a validated partial output.

## Lifecycle record publication

`metadata.json` is the current lifecycle document. Atomic replacement publishes complete snapshots; a step event journal supports observation. Final metadata contains typed business output and terminal state together. There is no directory coordination lock: callers serialize same-name execution and concurrent mutations.

## Rerunning a fixed name

The runtime verifies that an existing execution is stopped, rejects display replicas and unverified/foreign running records, then replaces current files while retaining `persistent/`. Anonymous generated-name collisions are rejected. Explicit reruns advance `started_at`; the directory is not an immutable history store. Consume/pin artifacts before replacing their producer.

## Waiting and termination

`wait_task` captures the current `started_at` internally and fails if it changes. Queries do not reconcile stale running states. Startup checks and explicit `kill` can settle confirmed dead local records. Permission errors and foreign processes remain unverified.

`axonx kill --task-id ID --timeout 5 --force false` verifies identity, stops descendants and the root execution, and rereads records. Children share the root's process. Remote kill uses the source machine and workspace, not a replica observer's mount path. No observation or deletion should be treated as process termination.

[Task contracts](../reference/task-contracts.md) · [Task management](../guides/task-management.md)
