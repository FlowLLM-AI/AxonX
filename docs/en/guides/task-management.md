# Task execution and observation

Execute a Task with the CLI on the machine that has its plugin and data installed. Local execution does not require an HTTP service:

```bash
axonx exec --task demo --task-name add-01 --x 1 --y 2
```

The command runs in the foreground, prints Task output and exits with the Task's exit code. Use your terminal or process manager for background execution. Each Task writes its configuration, progress, output and lifecycle state under `<workspace>/<task_type>/<task_id>/metadata.json`; demo's ID here is `base#demo#add-01`.

An observing service must use the same workspace and log directory as the execution process. It polls metadata and exposes read-only Task queries. The service does not restart or cancel independent Tasks. Startup and polling reconcile only confirmed dead original local Runs; live, foreign, replica and permission-unknown records retain their recorded state.

## Discover definitions

```bash
axonx exec
axonx list_installed_task_definitions
axonx get_task_definition --task demo
```

`exec` without arguments lists locally installed Tasks. The two definition Jobs query the selected service's installed environment. Studio's Task definitions page shows descriptions and input/output schemas without a launch form.

## Query status and logs

```bash
axonx list_task_ids
axonx list_task_statuses
axonx status --task-id 'base#demo#add-01' --detail full
axonx read_task_log --task-id 'base#demo#add-01' --offset -1 --limit 8192
axonx get_task_graph --task-id 'base#demo#add-01'
```

The Run ID is in metadata and status responses. Bind `read_task_log` to `--run-id` when inspecting an exact execution. Log offsets are bytes; use the returned offsets for subsequent reads. Studio groups records by Task type and registration, with search, state/type filters and 50 records per expanded group. Task lists and details provide observation without cancellation or deletion controls.

## Wait and follow

```bash
axonx wait_task --task-id 'base#demo#add-01' --run-id '<run_id from metadata>' --client-timeout 600
axonx stream_task --task-id 'base#demo#add-01' --stream true --client-timeout 600
```

Waiting checks the exact Run ID and reports the terminal outcome. Disconnecting an observation request does not stop a locally launched Task. A same-name replacement causes an exact-Run query to fail.

## Failures and reruns

The Runner publishes failures that reach Python cleanup. Abrupt process death can leave metadata at running; startup/polling and the next exec reconcile a confirmed dead original local Run to failed. Use explicit `axonx kill` for process termination; see [Task lifecycle](../concepts/task-lifecycle.md).

A fixed Task name reuses its Task ID and replaces terminal output while retaining Task-owned persistent data. Use a new name to retain a separate experiment. Coordinate same-name execution, deletion and synchronization externally; atomic metadata replacement does not serialize those operations.

For [Composite Tasks](composite-tasks.md), the parent executes children synchronously. Every child keeps its own metadata and identity while sharing the executing process. Successful execution is framework evidence; inspect research metrics and artifacts separately.

[Task API](../api/tasks.md) · [Lifecycle](../concepts/task-lifecycle.md)
