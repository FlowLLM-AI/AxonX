# Framework Extensions

Framework extensions suit scenarios requiring new long-lived dependencies, asynchronous interface steps, or call orchestration. Research algorithms are usually synchronous Tasks following the [existing development guide](../dev_guide.md); do not introduce service component lifecycles for purely research tasks.

![From configuration to framework composition](../../figures/reference/config-resolution.svg)

## Choosing an extension point

| Extension point | Typical responsibilities                                      | Execution and state                          |
| --------------- | ------------------------------------------------------------- | -------------------------------------------- |
| BaseComponent   | Connections, caches, external resources, managed dependencies | _start/_close, application lifecycle         |
| BaseStep        | Call components, combine results, emit events                 | async execute, a new instance for each Job   |
| PipelineJob     | Compose multiple Steps sequentially                           | Public Schema, defaults, final result        |
| BaseJob         | Custom event execution contracts                              | Implements stream(arguments, system) itself  |
| BaseTask        | Research data computation and artifact publication            | Synchronous steps; submit can start a worker |

A Job is asynchronous orchestration inside an Application; Task steps are synchronous functions. Both use similarly named Steps, but their base classes and execution boundaries differ.

Task repository backends implement `entries()` and `entry()` as isolated `TaskMetadata` snapshots. Their `summaries()` method returns isolated lightweight projections sorted newest first by creation time and Task ID; project directly from the index without copying complete inputs, outputs, or child records. `put_metadata()` persists and indexes the unified lifecycle record.

## Providers and local registries

`@provider("backend")` declares a class's implementation name. The framework's own axonx modules register as built-in; external Python classes only declare identity and do not automatically affect the global registry. Embedded applications must supply them to the current application through Application(providers=...) or a valid plugin manifest.

A (category, backend) pair cannot have different owners in the same registry. Repeated registration with the same implementation and owner can be idempotent. The registry freezes after composition. Names are part of the configuration contract and should not be guessed from class names.

## Runnable Component, Step, and Job example

This standalone script creates a formatter component in a temporary workspace, reads text through a Step, and returns formatted output without starting an HTTP service.

```python
import asyncio
import tempfile
from pathlib import Path
from axonx import Application, BaseComponent, BaseStep, provider
from axonx.components.job import ProgressEvent

@provider("prefix_formatter")
class PrefixFormatter(BaseComponent):
    component_type = "formatter"

    def __init__(self, prefix="AxonX: ", **kwargs):
        super().__init__(**kwargs)
        self.prefix = prefix

    async def _start(self):
        self.logger.info("formatter ready")

    async def _close(self):
        self.logger.info("formatter closed")

    def format(self, text):
        return self.prefix + text

@provider("format_text")
class FormatTextStep(BaseStep):
    async def execute(self):
        formatter = self.get_component("formatter", "default")
        self.response.answer = formatter.format(self.context["text"])
        await self.emit(ProgressEvent(name="formatted", percentage=100))

async def main():
    with tempfile.TemporaryDirectory() as directory:
        config = {
            "workspace_dir": str(Path(directory) / "workspace"),
            "log_dir": str(Path(directory) / "logs"),
            "log_to_console": False,
            "log_to_file": False,
            "components": {
                "formatter": {"default": {
                    "backend": "prefix_formatter", "prefix": "AxonX: "
                }}
            },
            "jobs": {
                "format": {
                    "description": "Format a text value.",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                    "steps": [{"backend": "format_text"}],
                }
            },
        }
        async with Application(
            providers=(PrefixFormatter, FormatTextStep), **config
        ) as app:
            response = await app.run_job("format", {"text": "hello"})
            assert response.success
            assert response.answer == "AxonX: hello"
            print(response.model_dump(mode="json"))

asyncio.run(main())
```

In Application, components start before Jobs and close in reverse order. Steps retrieve components during execution; avoid retaining self.context across requests or storing connections in module globals. The formatter must already be started before it can be called; the Step itself does not handle _start/_close.

## Declaring component dependencies

Use depend to declare relationships between managed components; ComponentGraph validates and injects them:

```python
@provider("report_cache")
class ReportCache(BaseComponent):
    component_type = "report_cache"

    def __init__(self, formatter="default", **kwargs):
        super().__init__(**kwargs)
        self.depend("formatter", formatter, PrefixFormatter)

    async def _start(self):
        self.logger.info(self.formatter.format("cache ready"))
```

Place this after the class definitions in the previous example and add the ReportCache class to providers and configure its named instance in components. The depend attribute must be a valid, unique identifier. When required=true, an instance name is mandatory. The expected base must declare a non-BASE category. Missing dependencies, type mismatches, and cycles fail before startup.

Failed startup rolls back resources that started successfully. Closing attempts every resource rather than stopping cleanup at the first exception. Resources partially allocated in _start should be releasable in _close so failed startup can also roll back.

## Parameters, defaults, and system

PipelineJob uses RuntimeContext: recursively merge defaults → caller arguments → system, then deep-copy the execution context. Nested overrides retain unspecified default fields; lists and scalar values are replaced. An empty object retains existing nested fields. Public parameters are first validated by JSON Schema; a Schema default does not automatically supply required parameters. defaults apply to the execution context and do not replace required validation of public inputs.

```yaml
jobs:
  format:
    parameters:
      type: object
      properties:
        text: { type: string }
      required: [text]
      additionalProperties: false
    defaults:
      internal_mode: simple
    steps:
      - backend: format_text
```

Steps can declare injected_parameters for framework-owned system fields. They must not conflict with public properties or be supplied by callers. agent_depth is a built-in example; public examples should not ask users to submit it. target is a reserved transport-selection field and cannot be declared as a Job business parameter.

## Events and results

Steps emit ProgressEvent, LogEvent, ArtifactEvent, or AgentMessageEvent through `await self.emit(...)` and set answer, success, and metadata through self.response. PipelineJob generates the final ResultEvent centrally, so ordinary Steps should not construct duplicate terminal events themselves.

The default event buffer holds 64 items. emit waits when it is full, providing bounded backpressure. Place time-consuming synchronous computations or file operations in threads, Task workers, or another suitable execution layer to avoid blocking the application event loop.

Exceptions from Steps are converted by the pipeline into failure results. Setting success=false prevents remaining Steps from running. Clients can determine business completion only after the final result; see the [event protocol](../api/events.md).

## Manifest extension boundaries

Plugins can contribute BaseComponent classes, JobConfig, and BaseTask. Component categories must match their declarations. Manifests describe backends; application configuration describes named instances.

The current plugin loader validates component classes against BaseComponent. BaseStep inherits only ComponentBase and cannot be loaded directly through manifest components.step. Inject custom Steps with `Application(providers=...)`. Plugin Jobs can compose built-in Steps; manifest `components.step` does not support loading BaseStep subclasses directly.

See [plugin manifests](../reference/plugin-manifest.md) for more package protocol details.

## Verification scope

Extension verification should cover actual risks: Provider conflicts, missing dependencies/cycles, startup rollback, aggregation of close errors, input Schema, consistency between ordinary results and streaming terminal states, and resource cleanup when consumers disconnect. For research Tasks, additionally verify typed input/output, failure status, and artifact paths.

After adding a backend, first verify it with a minimal Application(providers=...), then integrate the real service, plugin environment, and Studio form. A UI that can generate a form does not establish correctness of Task research logic.

Implementation references: `axonx/components/base.py`, `axonx/components/registry.py`, `axonx/core/graph.py`, `axonx/core/composition.py`, `axonx/steps/base.py`, `axonx/components/job/pipeline.py`, and `axonx/components/job/context.py`.

## Realtime collection, inference and reconciliation

`axonx.task.contracts` exports three optional authoring contracts:

- `BaseRealtimeApiTask` (`api`): implement `collect(window, budget)`. Return `None` to poll again, or a `WindowResult` with `done`, `skipped` or `incomplete`. Exceptions record a failed window and stop execution.
- `BaseInferenceTask` (`inference`): resolve a single model in `initialize_run`, set a nonempty `model_identity`, implement `inputs_ready` and `infer`. Input timeout records `incomplete`; data quality or history freshness exceptions record `failed` and stop execution. The model identity is copied at initialization for audit; plugins must keep the actual predictor fixed as well.
- `BasePredictionCompareTask` (`analysis`): implement `compare(key)` returning `PredictionComparison`. Outcomes are `consistent`, `different`, `protocol_mismatch`, `missing` and `error`. Exceptions are isolated per key; the task completes with a report even when individual comparisons fail. This contract does not inherit factor analysis rows/scores.

Window inputs contain ordered, uniquely keyed `ExecutionWindow` objects with timezone-aware `start_at` and `end_at`, plus a positive `poll_interval_seconds`. Window waiting and elapsed durations share `WindowClock`; tests may inject a fake clock. `DeadlineBudget.remaining_seconds` is monotonic and must bound every plugin request timeout, retry and backoff. Synchronous hooks cannot be forcibly interrupted by this helper. An already elapsed window is skipped; an uncommitted result finishing past the deadline cannot claim `done`.

Plugins can implement `window_skip_reason(window)` to skip a business-inapplicable window before waiting (for example, a closed market), while keeping its original schedule in the audit record.

`initialize_run` acquires owned resources, and `close_run` releases them after success, initialization failure or execution failure. Cleanup errors do not replace the primary exception. Process cancellation remains owned by the existing worker/task manager; plugins must not introduce another process scheduler.

Window outcomes, fixed model identity, and comparison results are published incrementally in `metadata.json.output_params`, including on failure. The Runner atomically publishes this single record; Studio reads it directly without a separate report file. The former `manifest.json`, `comparison.json`, `manifest_file`, and `report_file` contracts are removed without compatibility readers. Business datasets stay in explicit plugin directories; publish their data and metadata before a ready marker. Online publication uses the immutable store described below; quality checks, model normalization, market calendars and notification semantics belong to plugins. AxonX introduces no Tushare or model dependency.

Research plugins are responsible for algorithm validation and model equivalence.

### Immutable online publications

Use `OnlineStore` from `axonx.task.storage.online` to publish online data. Prepare artifacts in a temporary run directory, validate the report, and call `commit` with a `DeadlineBudget`. It copies new content into `persistent/online/commits/<commit_id>/`, shares identical immutable content across revisions, writes a frozen `history.json`, then atomically replaces `persistent/online/manifest.json`. The manifest swap is the only commit point. Exceptions or expired budgets leave the previous history intact. A deadline-bound publication lock rejects stale histories instead of overwriting newer commits; do not write to the store outside its Task lifecycle. Use the `prepare(commit, history_path)` callback for report construction and artifact checks before publication.

`OnlineCommit` records Task/Run IDs, signal date/time, consecutive revision, commit time, fixed model identity, prediction protocol and role-based artifacts with SHA256 hashes. `OnlineHistory.active(as_of)` selects effective revisions through a signal-date cutoff. Historical replacements retain original predictions and decisions, and make later portfolio reports stale until replayed. `report_is_current` detects this condition. Model upgrades may continue one strategy when feature and selection semantics agree; changed portfolio/feature semantics require a new Task name.

A committed `WindowResult` carries both `commit_id` and `committed_at`. A timely atomic publication remains `done` even if subsequent bookkeeping crosses the deadline. Uncommitted late results remain `incomplete`. The manifest is authoritative if a process dies between publication and lifecycle metadata persistence.

Stock plugins expose `StockOnlineReport` in `output_params.report`: commit, strategy identity, backtest dimensions, date range, portfolio settings, score selection, evaluation status and missing signal dates. Roles are `predictions` (raw current scores), `signal` (current final ranks), `signals` (effective ranks through the cutoff), `market`, `calendar`, `input_features`, `prediction_protocol`, `targets`, `orders`, `positions`, `trades`, `daily` and `summary`. Portfolio artifacts use the stock backtest schemas. Simulation outcomes are separate from actual broker executions; matured labels are evaluated later. Missing signal dates must remain visible even when missing quotes are configured as suspensions.

Publish the frozen history as `artifacts.signal_history`. Consumers use `pin_online_history(task, source_id, as_of=...)` to independently copy the manifest and its verified files, then `online_artifact` to resolve roles. The persistent manifest is authoritative even when the latest run failed or stopped before publishing its lifecycle metadata. Replay persisted final ranks rather than recomputing historical selections. A missed or closed-market run can expose the previous committed report with its original date and Run ID.

This replaces the JSONL signal journal, slot-prefixed artifact keys and inference `ready.json`; there are no compatibility readers or converters. Regenerate old online Tasks with a fresh Task name. Collection ready markers remain the input publication contract. Portfolio evaluation currently replays the effective history through the selected cutoff; it does not maintain an incremental broker account.

## Composite Tasks and cleanup

Use `BaseCompositeTask` for synchronous business sequencing, conditions and loops. Submit only the parent through the built-in `submit` Job. Children run in the parent's worker, inherit its instance name, and retain invocation records. Repeated calls of the same registration replace terminal outputs; consume file artifacts before replacement. Pass `source_tasks` explicitly for dependencies on other Task IDs. See [Composite Tasks](../guides/composite-tasks.md).

The plugin manifest registers Tasks. Deployment configuration can define thin `pipeline` Jobs and schedules:

```yaml
extends: default
jobs:
  refresh:
    backend: pipeline
    defaults:
      task: refresh_data
    steps:
      - backend: submit_task
schedules:
  refresh:
    job: refresh
    cron: "0 16 * * *"
```

Business Tasks own shared-data locks and business overlap policies. Composition does not supply distributed locking. Scheduler concurrency covers the Job invocation; a submission Job returns before the background Task completes. TaskManager supervises the accepted worker and owns shutdown and cancellation. Cancel the parent Run to stop its in-process children. Closing a submission Job does not cancel an already accepted Task.

Maintenance uses `list_managed_run_ids()` to select worker Runs owned by this service, including workers whose metadata is terminal or whose named Task was replaced. Backends that expose records from a shared workspace must override the default private-backend implementation. Return process ownership, not PIDs inferred from persisted metadata.

Task managers implement `cancel(task_id=None, run_id=None)`. At least one ID is required: `task_id` selects the current execution under the manager lock, while `run_id` selects an exact Run. Supplying both checks the current pair and returns false for a mismatch. To cancel an owned execution, pass its exact `run_id`.

Synchronous `BaseTask.close()` releases owned resources after step execution, including step and initialization failures. Cleanup failures preserve a primary step exception. `on_failure(error)` can persist business summaries when steps, output construction or cleanup fail; the runner still owns failed status. These callbacks cannot guarantee cleanup after forced process termination.

The built-in Tushare client owns and closes sessions it creates. `retry_rate_limit_forever=True` retries rate-limit errors at `rate_limit_retry_seconds`; other limits remain bounded. `query` and `query_has_more` accept an optional `DeadlineBudget` that caps waits and connection/read timeouts and is never forwarded to the API. Requests timeouts do not enforce a total wall-clock deadline: a slowly streaming response can overrun it. Budget checks after receiving, JSON decoding, DataFrame construction and page merging reject expired results; they do not interrupt in-flight network or CPU work. Without a deadline, unlimited rate retries continue until success or worker termination. Built-in DingTalk's `send_dingtalk_message` uses the same validated environment configuration as its notification Task.

## Stock portfolio policies

`BaseStockBacktestTask.portfolio_policy()` supplies an optional `PortfolioPolicy` to the shared stock execution ledger. Plugins implement `replacement_limit(n)` and `should_exit(rank=..., age=..., n=...)`; decisions receive only the current eligible-candidate rank and elapsed market days. The engine caps filled orders per side after initial entry, exits worst ranks first, and retains ownership of quote validation, cash, fees and artifacts. Policy positions have no fixed planned exit date. Policy exits are evaluated only on dates with recorded signals; dates without signals still update valuations and process security events. A signal day with no eligible candidates still evaluates exits with missing ranks. [Qlib Strategy](../../../plugins/qlib_strategy/README.md) uses this extension.

Stock backtest plugins can pass an optional `events` handler to `run_backtest`. It exposes `successors`, `reset(top_n)`, `apply(date, slot, book, cash, quotes) -> cash`, `blocked(code)`, and `pending_cash`. The engine loops over `top_ns`, resetting cash, holdings and event state before replaying all dates for each N. Quotes can be modified within that replay without affecting another N. Receivables must be finite and nonnegative; they count toward equity but are unavailable for purchases until settlement. The engine calls it before daily valuation/trading and checks it before purchases. Event facts and security-specific logic remain in the plugin. No handler preserves existing execution and artifact formats.

Scheduler backends implement `describe(*, include_history=False, history_limit=20)` for `list_schedules`: omit history/latest result by default and slice recent history before copying when requested. Task managers expose `list_restart_blockers()`, selecting queued/running schedule-origin Tasks from their owned Run IDs and lightweight summaries; shared workspace records alone do not establish ownership. `source` belongs to framework execution metadata and must survive worker handoff and child execution.

Cron schedules accept `history_retention_days` (positive integer, default `7`). On startup and each history write, expired finished trigger records are removed from `schedules/<hash>.json`; running triggers are retained. Age is measured from `finished_at`, falling back to `triggered_at` for older records, with timezone-less values interpreted as UTC. This replaces the previous 50-finished-trigger limit and does not delete Task directories, artifacts or logs. Cleanup occurs on these writes, without a separate background timer.

### Shared workspaces and execution ownership

A workspace repository lists all valid Task records, including records written by other services and direct `exec` processes. Reading a record never adopts its worker. `TaskView` (full list/detail responses) and `TaskSummary` add a query-only `managed_run_id`: a supervised root Run points to itself, its exact in-process children point to that root, and unowned records return `null`. These fields are never persisted in `TaskMetadata`. Cancellation is available only for an active root Run managed by the selected service; cancel its root to stop a child. Terminal records can still belong to a worker finishing cleanup.

Each cron scheduler has a runtime `scheduler_id`, also included in its Task `source.schedule`. Match this ID when linking Task history to a current schedule, rather than matching its name. The field is optional in persisted records, so existing records remain readable and are shown as unlinked workspace history. Older AxonX readers that reject unknown source fields must be upgraded before sharing newly written scheduled records. Scheduler `running` and `last_trigger` describe Job invocations on that service, not the lifetime or outcome of submitted background Tasks. `forbid` and `replace` retain their Job-level semantics; they do not provide cross-service schedule deduplication or cancellation of already accepted Tasks.

Maintenance closes admission to new local cron triggers before checking active scheduled Jobs and managed Runs; rejection restores admission. Active local scheduled Jobs and scheduled root Runs block even forced maintenance. Other services' records do not block maintenance. Shutdown first stops admission and signals only managed worker process groups, then awaits component cleanup in reverse dependency order. Task managers owning local subprocesses can override the synchronous `request_shutdown(force=False)` hook to stop admission and signal workers without waiting for Jobs or filesystem cleanup; `force=True` must target only tracked worker groups, including descendants whose leader has exited. The hook must be nonblocking and safe to call from a signal handler or the shutdown watchdog thread. A failed hook does not prevent other managers from being signalled or remaining resources from being closed. HTTP service shutdown has a total `cleanup_timeout` deadline; another Ctrl+C or deadline expiry forces process exit, which may leave lifecycle records incomplete. Startup does not infer failure or adopt workers from persisted PIDs. Interrupted, unowned records therefore retain their recorded state until explicitly repaired.

Local runners hold an advisory Task-directory lock through final publication and cleanup. Directory creation/reset, Task deletion, workspace deletion and replica application coordinate workspace mutations; terminal directories still leased by a runner cannot be reset or deleted. Workspace deletion also protects active Task files and their ancestors. Accepted queue publication and outcome settlement finish before cancellation releases their mutation locks. Locks live in `.locks/` outside Task directories and must not be removed while services are using the workspace. These locks require a filesystem implementing shared POSIX advisory locks, and do not replace business-data locks or coordinate older writers that do not participate.

Update records now live under `updates/<service-key>/<update-id>/`, where the service key uses the hostname, bind address, port and startup directory. A service only recovers its own interrupted updates. Legacy `updates/<update-id>/` records are retained on disk and are not modified or included in the latest service-scoped status query; explicit reads by update ID remain available.
