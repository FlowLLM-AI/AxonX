# Architecture Overview

AxonX separates application capabilities, synchronous research and file evidence.

![AxonX interfaces, commands and core capabilities](../../figures/getting-started/overview.svg)

## Responsibilities by layer

| Layer       | Responsibility                                    | Owning modules |
| ----------- | ------------------------------------------------- | -------------- |
| Clients     | JSON, SSE, uploads, MCP                           | `axonx.client` |
| Application | Config, dispatch, providers, managed lifecycle    | `axonx.app`    |
| Daemon      | Supervised service, scheduled processes, updates  | `axonx.daemon` |
| Plugins     | Installed Task registrations and wheels           | `axonx.plugin` |
| Tasks       | Typed authoring, execution, records and artifacts | `axonx.task`   |

## Execution chain for queries

A client calls `/jobs/status` with `task_id`. Authentication and Dispatcher validate the request. The Job Step reads through `task_index`, returning a `JobResponse`. The index observes files; reading a record does not execute or repair a Task.

## Execution chain for research

Local CLI `exec` discovers Task registrations and resolves execution settings, then constructs the Task and calls `TaskExecutor`. Synchronous steps and children run in that process. The executor persists metadata/progress, closes resources, validates output and publishes final state. CLI waits and returns output/exit code.

Remote native commands go through the target's `cli` Job, which launches the configured AxonX command in a new process at the service workspace, streams stdout/stderr and cleans up its process group. Scheduled `exec` commands are launched through the daemon and survive replacement of the application service. These are distinct process owners.

## Application assembly

`Application` composes configured providers in a local registry, injects typed dependencies and starts managed components in topological order; it closes them in reverse order. Framework extensions use `providers=...`. Startup supplies the TaskCatalog, update backend and scheduled-command launcher explicitly. Embedded applications can omit product adapters; Cron requires a host launcher.

## Plugins and Agents

Plugin manifests register Tasks only. Installing code changes the chosen Python environment; it does not refresh the persistent service's registration snapshot or cached classes. Remote installation explicitly builds, uploads, installs and cleans up, followed by restart/verification.

Agents use CLI or configured Job tools to inspect the same evidence. The built-in Claude backend owns SDK sessions and appends the canonical development guide. Research execution is independent of an Agent turn.

## Design boundaries

- `upstream_task_ids` declares input dependencies; `parent_task_id`/`children` records invocations. Neither launches a whole DAG automatically.
- Task queries are observations. Runtime startup/termination reconciles confirmed dead local processes.
- Caller coordination protects same-name writes; atomic metadata replacement is not a lock.
- Display synchronization copies bounded evidence, not active processes, environments or an entire workspace.
- Each target has its own interpreter, files and service configuration. Explicit CLI targets connect directly; Studio can use configured backend forwarding.

[Jobs and Tasks](jobs-and-tasks.md) · [Task contracts](../reference/task-contracts.md) · [Framework extensions](../development/framework-extensions.md)
