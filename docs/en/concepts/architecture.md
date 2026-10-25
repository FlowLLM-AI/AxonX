# Architecture Overview

AxonX separates capability calls, research execution, and result storage. The CLI, Studio, and external Agents call Jobs; asynchronous Job Steps access components; research runs as synchronous Tasks in independent CLI processes. Once results reach the workspace, task queries and Studio use the same records.

![AxonX architecture layers](../../figures/concepts/architecture.svg)

## Python module boundaries

The package has seven subsystem roots. Existing useful subdirectories under `app` and `task` are retained.

| Module   | Responsibility                                                                                                              |
| -------- | --------------------------------------------------------------------------------------------------------------------------- |
| `app`    | Service configuration, composition, Components, Jobs/Steps, HTTP/MCP, Agents, service repositories and workspace operations |
| `cli`    | Executable entry point, command routing, local commands and presentation                                                    |
| `daemon` | Standalone supervision, local control and owned update subprocesses                                                         |
| `cron`   | Crontab code and configuration; a supplied callback launches commands                                                       |
| `task`   | Independent Task execution, records, research contracts, artifacts and replica processing                                   |
| `plugin` | Task manifests, discovery, wheel build, installation and removal                                                            |
| `common` | Generic config/env/runtime/connection mechanisms, registration, process identity, files, logs and async utilities           |

Dependencies point from callers to capability owners: `app` uses Task data interfaces and Common mechanisms; `task` uses `plugin` and Common mechanisms; `plugin` uses Common mechanisms. `common` imports none of these subsystems. CLI imports App for service and remote calls; local exec/kill and the cron worker stay App-free. App configuration models and YAML live in `app/config/`; shared loading mechanisms live in `common`. Cron does not import the daemon. Daemon workers remain standalone standard-library programs. See the [refactor plan and verification](../development/module-refactor.md).

## Responsibilities by Layer

Regular HTTP calls and SSE event calls pass through the same Job capability layer. MCP maps public Jobs to tools and returns regular responses. SSE is a separate HTTP endpoint for live events; these are different transports.

## Execution Chain for Queries

Using `status` as an example:

CLI or Studio → Job → query Step → Repository → published `metadata.json`.

A query does not execute the Task again. Repository watches workspace records and provides the current index to callers; observing file changes and executing workers are separate responsibilities.

## Execution Chain for Research

Using `axonx exec --task demo` as an example:

CLI → `TaskExecutor` → `TaskRunner` → synchronous Task steps → atomic lifecycle record and artifacts. Task progress events belong to Task schemas; the Job layer reuses them for transport.

## Application Assembly

Application creates Components and Jobs from configuration and registries. Components declare dependencies through `depend`; the application starts them in topological order. Normal shutdown closes them in reverse dependency order, while startup failures roll back objects already started. The daemon starts the separate service and cron workers; cron requests independent exec processes through its launch callback.

## Plugins and Agents

Installation changes the selected Python environment without refreshing loaded service modules or tracking restart requirements. New CLI processes load the installed environment. Restart a persistent service when it must reload Task schemas, Components, or Jobs; existing processes are not version-isolated. Plugin environment mutations are not serialized.

AxonX supplies the quantitative research Harness: Task contracts, execution, records, and artifact queries. The model/tool loop and conversational context are managed by the external Agent host or the built-in Claude Agent SDK backend. With a Skill or development guide, source access, and code tools, either Agent path can develop plugins and use Task evidence for iteration. The built-in Agent is a component whose capabilities depend on Job tools, SDK tools, working directory, and permission mode. Research Tasks can execute independently of Agent.

A remote service is another complete Application with its own plugin environment, workers, and workspace. Studio forwards remote operations through the local backend, while an explicit CLI `--target` connects directly to the target.

## Design Boundaries

- `source_tasks` records upstream relationships; the framework does not automatically execute the entire DAG.
- Repository indexes can be rebuilt from records; artifact files and plugin environments must be preserved separately.
- Synchronization copies terminal Task directories, without migrating active workers or copying the entire workspace.
- Resource queries provide machine readings, without automatic machine selection or GPU scheduling.

## Further Reading

- [Jobs and Tasks](jobs-and-tasks.md): the two execution abstractions and how to choose between them.
- [Workspace](workspace.md): file formats and recovery boundaries.
- [Remote Machines](../guides/remote-machines.md): the two remote call paths.
- [Framework Extensions](../development/framework-extensions.md): component and orchestration extensions.

Implementation entry points: [Application](../../../axonx/app/core/application.py), [TaskRunner](../../../axonx/task/runtime/runner.py), [HTTP assembly](../../../axonx/app/components/service/http/app.py).

App does not import research plugins. It reads Task contracts/workspace data and triggers local process reconciliation; definitions use a CLI subprocess. Common owns generic registration/process mechanisms, Task owns lifecycle policy. See [module refactor](../development/module-refactor.md).
