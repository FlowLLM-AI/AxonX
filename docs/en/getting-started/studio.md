# Using AxonX Studio

## Open Studio and configure the connection

![AxonX Studio 0.3.0 home](../../figures/studio/home.png)

[Full-resolution screenshot](../../figures/studio/home.png)

Screenshots use the complete English Studio 0.3.0 interface at twice the browser's pixel density. Playground provides fictional data and simulated execution; real services expose their installed Tasks and configured machines.

Install axonx[studio] or build/install axonx_studio from source, then start `axonx app`. Open http://127.0.0.1:1024 and set the service token in browser settings. The UI can load even when authenticated data Jobs are unavailable. Select the intended machine before execution or file changes.

## Research and development entry points

Current navigation groups are System management, Daily operations, Research, and Development tools. System management contains All tasks, Machine resources, Environment, and Workspace. Development tools contains Task definitions and API interfaces. Research contains Agent, research results, and Strategy comparison; Daily operations groups online, comparison, and data-update reports.

## Execute a Task and inspect details

![Studio task definitions, input parameters and expected output](../../figures/studio/task-definitions.png)

[Full-resolution screenshot](../../figures/studio/task-definitions.png)

The screenshot selects `playground_train` in the static Playground. On a real service, select the installed Task you intend to execute.

Open **Development tools → Task definitions**, select demo, read its schema and fill x/y plus an optional task_name. Execute launches the service's cli command and displays output. The command connection and persisted metadata are tracked separately. Successful process creation is not success: inspect the terminal command result, Task state and business output. A connection failure is reported separately and should be investigated before retrying.

Task details show started_at, steps, logs, children, inputs/outputs and relationships. Stop uses CLI kill after checking the current start identity. Children share the root execution process. Deleting a directory does not stop its writers.

## Workspace and resources

![Studio workspace tree and Markdown preview](../../figures/studio/workspace-preview.png)

[Full-resolution screenshot](../../figures/studio/workspace-preview.png)

Workspace is under System, with route `#local/workspace/files`. Browse directories, load additional entries and preview text/structured/table formats. Markdown previews provide rendering and a bounded source view. Paths belong to the selected workspace; delete only after checking writer state. Machine resources show observed CPU/memory/GPU without automatic device allocation.

## View research results

ETL, factor, training, prediction and backtest pages read metadata and published artifacts. Strategy comparison requires compatible dates, protocols and universes. Online/comparison/data operation pages select report_kind-based Task reports. Missing/omitted replica files or incomplete market data need explicit interpretation; Task success alone does not prove complete research evaluation.

Research screenshots use Playground's synthetic Tasks and artifacts in the current interface. They illustrate the controls and fields; their metrics are fictional. See [Research results](../research/results.md) and [Backtests](../research/backtest.md).

## Agent and API entry points

![Studio API catalog with get_task_def request and response](../../figures/studio/api-catalog.png)

[Full-resolution screenshot](../../figures/studio/api-catalog.png)

Agent requires backend model configuration and supports stored sessions, presentation patches and turn interruption. Independent research execution has its own lifecycle. API interfaces use the current Job catalog. Use get_task_def for definitions; execute a native command through cli argv. For remote plugin deployment follow explicit build/upload/install/cleanup, not a local path in a remote command.

## Page links and preferences

Routes use `#machine/section/view/resource`; routeHash encodes resource IDs containing #. Task definition example: `#local/task-defs/catalog/demo`. Browser language/theme/panel preferences do not change server research configuration. Switching machines must preserve the selected target in each request and avoid stale responses.

## Empty states and failures

An empty fresh workspace is expected. Run Demo to obtain evidence before research setup. For 401 check the local token; for missing definitions confirm target plugin installation and restart the persistent catalog. For missing charts inspect artifact contracts and file coverage. A loaded static page does not prove backend readiness.

[Quickstart](quickstart.md) · [Task management](../guides/task-management.md) · [Plugin deployment](../plugins/management.md) · [Agent configuration](../agent/configuration.md)
