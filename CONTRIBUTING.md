# Contributing to AxonX

English · [简体中文](CONTRIBUTING_ZH.md)

We welcome bug reports, feature requests, documentation improvements, research plugins, and code contributions.


The application uses cohesive capability files: machine observation and diagnostics share `components/machine/inspection.py`; Task summaries and lineage share `components/task_index/query.py`; Job result folding and response completion share `components/job/response.py`. Pipeline invocation state stays private to `pipeline.py`. Workspace paths, previews and uploads live in `core.py`, `preview.py` and `uploads.py`; uploaded files are accessed through `workspace.uploads`. Common, synchronization and Task-query Steps are grouped by capability. Task context queries belong to Task Steps. The complete application file inventory is maintained in `module-dependencies.md`.

## Before you start

Search [existing issues](https://github.com/FlowLLM-AI/AxonX/issues) and related code. For bugs, include reproduction steps, expected and actual behavior, environment versions, and relevant logs with credentials removed. For features, explain the research or development problem and the desired behavior.

Use the bug report, feature request, or usage question form, or a free-form issue for other topics. For bugs, distinguish reproduced failures, intermittent observations, and static-analysis suspicions; identify the affected area and local or remote target. Share sanitized excerpts rather than the entire `.axonx/` workspace.

For changes to public CLI/API/configuration contracts, persisted task records, or task lifecycle behavior, discuss the design in an issue before a large implementation. Keep each PR focused on one coherent problem.

## Find the right area

| Location                                          | Responsibility                                                            |
| ------------------------------------------------- | ------------------------------------------------------------------------- |
| `axonx/`                                          | Application composition, Components, Jobs, CLI, service, and Task runtime |
| `plugins/`                                        | Research Tasks, algorithms, plugin manifests, and plugin tests            |
| `axonx_studio/`                                   | Browser UI, API client, task forms, and research charts                   |
| `tests/`                                          | Framework unit and integration tests                                      |
| `docs/en/`, `docs/zh/`, `docs/figures/`           | Bilingual guides and shared screenshots/diagrams                          |
| `docs/.vitepress/navigation.mjs`, `github-pages/` | Documentation navigation, theme, and site build tooling                   |

See the [Task development guide](https://flowllm-ai.github.io/AxonX/en/dev_guide), [framework extensions](https://flowllm-ai.github.io/AxonX/en/development/framework-extensions), and [plugin manifest](https://flowllm-ai.github.io/AxonX/en/reference/plugin-manifest) for implementation contracts.

## Module boundaries

| Module   | Allowed repository dependencies                                              | Public boundary                                                    |
| -------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `utils`  | None                                                                         | `async_work`, `env`, `logging` and `values`; environment loading is explicit     |
| `task`   | `utils.env`, `utils.logging`, `utils.values`                                 | Task authoring, data contracts, execution and storage              |
| `plugin` | None      | Discovery, installation and Task registration data            |
| `app` | Task models/storage APIs and injected catalog (type only); `client`; shared utilities | App-owned components, Jobs, transports and Workspace |
| `client` | Task event models; shared utilities | Public service contracts and caller-owned HTTP/MCP connections |
| `daemon` | Launcher: App, Task settings/catalog, Plugin discovery and Client connection contracts; supervisor: standard library only | Restart one application service and reap scheduled exec processes  |
| `cli`    | Other modules public entry points                                            | Parse arguments, route calls, render results and return exit codes |

Task models and enums must not import execution, storage or plugin code. Task execution never imports App, Plugin or CLI. Plugin discovery lives in `axonx.plugin.discovery`; `discover_task_registrations()` reads Task registrations without computing content fingerprints. `axonx.task.runtime.catalog.TaskCatalog` merges these registrations with built-ins, validates conflicts and resolves classes on demand. CLI and service startup assemble their own catalog snapshots; callers construct the root Task and pass it to `TaskExecutor(resolve_task=resolver).execute(task)`. The executor uses that resolver to construct and execute child Tasks and binds an execution callback while the parent runs; Task classes do not import the executor or retain a resolver.

`axonx/task/` contains only `__init__.py` and five capability packages:

| Package    | Responsibility                                                                                |
| ---------- | --------------------------------------------------------------------------------------------- |
| `models`   | Data contracts, enums, identity rules and parameter validation                                |
| `core`     | Task authoring bases, composition, execution windows and business clocks                      |
| `runtime`  | Task catalog resolution, execution, progress, process control, lifecycle reconciliation and replay |
| `storage`  | Workspace layout, metadata, event/log files, artifact snapshots, publication and history      |
| `builtins` | Concrete Tasks and domain implementations                                                     |

Runtime dependencies flow from `runtime` to `builtins`/`core`/`storage`/`models` and from `core` and `builtins` to `storage`/`models`; built-ins also use authoring bases in `core`. Storage depends only on models within Task. The `DeadlineBudget` annotation in online storage is a type-only dependency on `core.clock`. The Task root initializer documents its capability packages without importing them or defining an export facade. Import capabilities explicitly from their owning modules. The runtime package loads only execution settings, so reading settings does not import the executor; model packages expose data contracts without execution or storage side effects. Use `task.models.identity` for enums and identity rules, and `task.models.base` for shared model policy and calendar-date validation. Process termination and stale-record settlement belong to `task.runtime.lifecycle`; storage only supplies the required reads and writes.

Task data contracts are organized by responsibility within `task.models`:

| Module      | Responsibility                                                                |
| ----------- | ----------------------------------------------------------------------------- |
| `base`      | Shared `TaskModel` policy and calendar-date validation                        |
| `identity`  | Task types, states, naming and upstream Task IDs                              |
| `params`    | Inputs, outputs, training curves, comparisons and execution windows           |
| `artifacts` | Artifact references, protocol headers, model collections and replay manifests |
| `lifecycle` | Task metadata, step status, children and display-replica records              |
| `execution` | Immutable invocation identity and typed child results                         |
| `events`    | Log chunks, progress/log events and discriminated event parsing               |
| `reports`   | Online commits, frozen history nodes and shared backtest reports              |
| `query`     | Catalog, summaries, graphs and context projections                            |

Pydantic contracts inherit `TaskModel` and reject undeclared fields. `Protocol` explicitly permits plugin-defined payloads; `TaskMetadata` remains closed. Cross-field checks stay with the model that owns the invariant. These modules perform no storage or execution operations. Import models from their owning module; removed module paths have no compatibility aliases.

Task ownership follows behavior and domain, not Python syntax. Shared data contracts belong to `models`; Task templates belong to `core`; execution and replay drivers belong to `runtime`; filesystem access belongs to `storage`; business-specific types and rules belong to `builtins`. `models.lifecycle` owns invocation identity and child results. `models.artifacts.ReplaySource` describes inputs, `storage.replay.ReplayStream` owns their snapshots, and `runtime.replay` owns deterministic time and event delivery. `models.reports.HistoryNode` defines the frozen history format. Source-directory and input-path validation live in `storage.inputs`, with thin Task authoring helpers. Prediction protocol construction takes a caller-supplied file revision and performs no I/O. Stock report contracts, signal-format constants and stock-only validation live in `builtins.stock`; generic online commits do not enforce stock formats. App owns display-replica preparation, sampling, archive planning, transfer, indexing and application in `app/components/sync`; internal plans and both transfer and archive-application results live in its `models.py`. Task retains display-replica data contracts and read-only enforcement.

### Task authoring and extensions

Task identity is derived from `task_type`, required `reg_name`, and the resolved `task_name`; constructors do not accept a separate `task_id`. `upstream_task_ids` is an ordered array of Task IDs in Python inputs and metadata. The CLI accepts comma-separated text or a JSON array and converts it before construction. Lifecycle states are `running`, `succeeded`, and `failed`; explicitly terminated executions settle as failed. `report_kind` is the sole presentation selector; operation pages select standalone `online` inference, `online_pipeline`, `compare_pipeline`, or `data_update`. Metadata reads validate the current structure without legacy field conversion and leave files unchanged.

`task/core` contains five files. Import classes from their owning module:

| File          | Capability                                                                                                                             |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `base.py`     | `BaseTask`, `TaskStep` and `ChildTaskError`; inputs, identity, child calls, output and runtime callbacks                               |
| `research.py` | ETL, Analysis, Train, Predict and Backtest bases, plus incremental `BasePredictionCompareTask` reports                                 |
| `windows.py`  | `BaseWindowTask`, `BaseRealtimeApiTask`, `BaseInferenceTask`; window scheduling, collection, fixed-model inference and partial results |
| `clock.py`    | Real business time (`WindowClock`) and monotonic deadlines (`DeadlineBudget`)                                                          |
| `__init__.py` | Module-by-module documentation, explicit child-module imports and `__all__`                                                            |

Declare `input_cls` and `output_cls`, yield synchronous methods from `build_task_steps()`, and return the declared output model from `build_output_params()`. The step generator is lazy, so later branches can read `self.state` populated by earlier steps. Use `report_progress()` for progress. Release resources in `close()`, which the executor also calls after failed initialization or rejected startup. Cleanup errors do not replace a primary failure. `on_failure(error)` records business details; the executor owns lifecycle status. Final output is built after cleanup, so retain the data needed to build it. Call `publish_output()` during a step to persist a typed snapshot without completing the Task; its `build_output_params()` hook must be repeatable.

Any Task can call `run_task("registration", **inputs)` in their steps and consume `ChildTaskResult.output_params` or `.output` explicitly. Use ordinary Python conditions, loops and retries. The default policy stops on failure; `on_error="continue"` permits later children while keeping the parent failed. `children` exposes defensive snapshots. Children inherit the workspace, timezone and business clock. Invocation records use `reg_name` and `child_task_id`; the child stores its caller in `parent_task_id`. Results expose the invoked ID as `ChildTaskResult.child_task_id`.

Use upstream/downstream for input dependencies: `BaseInputParams.upstream_task_ids` is an ordered list of direct upstream Task IDs, and `upstream_task_id(TaskType.TRAIN)` requires exactly one upstream of that type. Graph nodes expose `upstream_task_ids`; context relations expose `direct_upstream`, `all_upstream` (direct and transitive), and `direct_downstream`. Downstream links are derived from declared upstream IDs. Use parent/child only for Task invocations recorded by `parent_task_id` and `children`. One Task's children may depend on one another, but neither containment nor invocation order creates a dependency: pass `upstream_task_ids=[previous.child_task_id]` explicitly to `run_task()`. Input dependencies do not schedule Tasks or establish execution ownership.

Window inputs (`ExecutionWindow`, `WindowInputParams`) live in `models.params`; `WindowResult` lives in `models.reports` with training curves and prediction comparison details. Implement `execute_window(window, budget)` for a generic window Task, or `collect(window, budget)` for realtime collection; returning `None` from the collector polls again within the budget. Inference implements `initialize_run()`, `inputs_ready(window)` and `infer(window, budget)`, setting one nonempty `model_identity` during initialization. Extend `validate_run()`, `window_skip_reason(window)` and `build_output_params()` for validation, business exclusions and extra output. Release resources through the same `close()` hook.

Windows execute in start order and publish each outcome, including missed windows, input timeouts and deadline overruns. Exceptions retain earlier results and stop the Task. Business outcomes `incomplete` and `skipped` do not fail the Task by default. An uncommitted result returned after the deadline becomes incomplete; committed results are checked against their recorded in-window commit time. Bound requests and retries by `budget.remaining_seconds`, wait with `budget.sleep()`, and call `budget.check()` before publication. A budget cannot forcibly interrupt a blocking request.

Import `ReplayClock` from `task.runtime.replay` and pass `clock=ReplayClock(aware_datetime)` to replay business time; the default clock uses real time. Creation, lifecycle timestamps and performance measurements remain real. Only the thread creating a replay clock may advance it. Deadlines and window ordering compare UTC instants, including repeated local times during daylight-saving transitions.

Invocation identity and child results are `models.lifecycle.TaskContext` and `ChildTaskResult`; the context contains no logger or service handles. The Task retains its logger. Migration: `core.task` is now `core.base`; `core.standard` and prediction comparisons from `core.compare` are now `core.research`; realtime and inference bases moved from `core.realtime` and `core.inference` to `core.windows`. The internal `_WindowTask` is now public `BaseWindowTask`, and window cleanup uses `close()` instead of `close_run()`. Removed paths have no compatibility modules.

Resident components stay in App: `components/task_index` owns polling, caching, subscriptions, lineage, summaries and event streams, `components/sync` owns replica preparation, transfer, indexing and application, and `components/updater` owns application admission and response completion. App builds record queries from Task models and storage APIs. Service startup injects one `task.runtime.catalog.TaskCatalog` into App. Task-definition Jobs query that snapshot in a worker thread and load Task classes on demand; queries neither rediscover plugins nor invoke CLI subprocesses. Embedded hosts pass `task_catalog=` explicitly to enable definition queries. Restart the service after plugin installation, upgrades or source changes to reload definitions. Task execution remains in `exec`. Observation leaves Task records unchanged; startup and explicit termination can settle confirmed exited local processes. Receiving archives and querying replica indexes work without a configured outbound sync component or target. CLI contains no resident components or Steps.

Service clients and their public contracts live in `axonx/client`. `config.py` owns connection options, address normalization, defaults and wire conventions; `models.py` owns Job responses/catalogs and staged-file results; `events.py` owns the public stream envelope and Agent message patches, reusing Task log/progress contracts from `task.models.events`. `base.py` owns connection lifecycle, `RemoteServiceError` and `RemoteConnectionError`; `http.py` owns HTTP/SSE, uploads and short-lived invocation helpers; `mcp.py` owns MCP calls. The package initializer is a namespace without eager imports or root re-exports. Import implementations explicitly, for example `from axonx.client.http import HttpClient` and `from axonx.client.mcp import McpClient`. App consumes these contracts and retains Job execution, event folding, authentication policy, sessions and workspace operations. Client never imports App; importing a contract never loads HTTP/MCP transports. Task models and artifact protocols remain in Task.

MCP uses FastMCP >=4.1.4 and MCP SDK >=2.3.0. Use the current snake_case SDK fields without compatibility branches; MCP health checks verify tool discovery.

The local CLI commands are `app`, `exec`, `kill` and `plugin`; Task-definition queries are service Jobs named `list_task_defs` and `get_task_def`. Root help (`axonx`, `--help`, `-h`) stays offline. Existing daemons retain their startup argv, so relaunch the whole daemon after a CLI entry-point migration. Ordinary Jobs connect directly to the selected service, including explicit remote targets. Only remote native commands use the `cli` Job. `exec` and `kill` share execution configuration: explicit CLI fields override `get_config`, then model defaults apply. Only connection failures fall back; authentication, protocol and Job failures propagate. The config Job returns absolute workspace/log paths and omits Cron runtime callbacks. Execution settings are no longer transported through dedicated Task environment variables. CLI has five implementation modules: `parser.py` owns command inputs, connection options, plugin syntax, cron validation and offline help; `commands.py` adapts local service, Task and plugin operations; `remote.py` invokes service Jobs and forwards raw CLI commands; `rendering.py` serializes results and streamed event blocks; `main.py` routes commands and handles errors. `__init__.py` exposes the Python entry point and parser, and `__main__.py` supports `python -m axonx.cli`. `Command` keeps parsed inputs and raw arguments because plugin commands and remote targets parse their own grammar. Plugin failures use the same exit policy as other commands: invalid inputs return 2, operation failures return 1.

The `app/` root contains only `__init__.py` and five capability packages: `components`, `config`, `core`, `steps` and `workspace`. Package initializers contain documentation only; import each implementation or contract from its owning module. `core` assembles, starts, stops and dispatches the application. `components` owns capability implementations and resources; `steps` adapts Job invocations to them. Machine metrics, build identity and Python execution live in `components/machine`; service-owned CLI execution and response-completion callbacks live in `components/job`. Domain data, enums and pure validation live in each capability's `models.py`; model imports must not load execution or transport implementations. Provider lookup lives in `components/registry.py`, component categories and dependency declarations in `components/models.py`, and shared application defaults in `config/defaults.py`.

App owns configuration, registry, Workspace and the startup banner. Workspace provides file operations without Task-specific hiding or deletion policy. The configured `command` vector supplies the external command driver; an injected update backend owns prepare/commit/status. `daemon.launcher` creates one Application with explicit `task.runtime.settings.ExecutionSettings`. The top-level `cron` list contains `expression` and `command` strings and defaults to `[]`. Schedules share application configuration discovery, inheritance, environment expansion and overrides; an inherited list is replaced as a whole. `CronConfig` validates five-field expressions and parses argv without a shell. CLI supplies command validation; the launcher checks every command before starting the daemon. Only local `axonx exec --task NAME` commands are accepted. The runtime-only `launch_scheduled` callback is passed separately to `Application`; configuration contains no callbacks. Restart to apply schedule edits; missed slots are not replayed.

```yaml
cron:
  - expression: "0 16 * * 1-5"
    command: "axonx exec --task download_tushare_task --days-back 7"
```

The daemon supervises only the application service. Manual CLI children stop with that service; their execution never delays a restart beyond the cleanup deadline. Scheduled exec processes are created and reaped by the daemon and run to completion across service restarts. Updates reject new scheduled launches, stop the service and manual children, run the updater, then start a fresh service that rereads the application configuration and schedules. In-place updates do not freeze code or dependencies for existing Tasks. `daemon.supervisor` uses only the standard library and receives complete command, working-directory, environment and log-file values; it does not interpret schedules or restart completed Tasks.

Cancellation-safe async cleanup and blocking work belong to `utils/async_work.py`, shared by App, Client and Daemon. Application YAML/JSON loading, inheritance and merging belong to `app/config`. Environment loading and interpolation live in `utils/env.py`; scalar conversion is shared through `utils/values.py`. Log configuration, retention and argument formatting live in `utils/logging.py`; App owns the cleanup schedule, and Task owns execution log scopes and log reading. Schedule models belong to `app/config/models.py`; `components/cron` owns only scheduling and lifecycle. Application configuration lookup, inheritance and overrides use `app/config/loader.py::ConfigLoader`; installed `axonx.configs` entries target a package and an optional configuration file stem. Command-line option grammar belongs to CLI. Workspace operations return their models from `app.workspace.models` directly: `WorkspaceListing`, concrete `FilePreview` variants, `DeletedEntry`. Staged uploads return `client.models.StagedFile`. Entry filters receive `WorkspaceEntry` objects. Job and HTTP adapters use those results directly and serialize them at the transport boundary.

Task owns atomic writes, revisions and snapshots in `task.storage.files`, online publication locking in `task.storage.files`, and exact process inspection in `task.runtime.process`. Plugin owns its checksums. App keeps the small atomic write needed for upload staging. Task metadata has no coordination lock; callers serialize competing mutations of the same Task directory. Preserve online publication consistency and Daemon's singleton lock. These module moves have no compatibility imports.

Task storage uses seven capability modules: `files.py` owns atomic writes, revisions, snapshots and publication leases; `workspace.py` owns directory layout, lifecycle records and metadata scans; `artifacts.py` owns artifact records and verification; `inputs.py` owns successful upstream records and input/model-collection snapshots; `logs.py` owns `TaskJournal` and `TaskLogReader`; `online.py` owns `OnlineStore` and frozen history chains; `replay.py` owns `ReplayStream`. The package initializer introduces and exports all seven child modules, while retaining the shared Task-record operation exports. Unchanged metadata records are reused; incomplete records retain the last valid indexed value until they can be read again. Snapshot revisions are checked before replacing their targets. Successful upstream reads use `storage.inputs.read_upstream_metadata(workspace, task_id)`, returning the Task directory and complete metadata after validating the protocol, directory identity, successful state and display-replica policy. Input pinning still rechecks the source and artifact revisions.

## 1. Contribute to the AxonX framework

Use this path for the runtime, CLI, HTTP/MCP services, and shared extension points in `axonx/`, plus Studio and framework tests. Follow the Plugin contribution path below for research Tasks and algorithms.

### Development setup

Fork the repository and clone your fork. From its root, use Python 3.12+ on macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

For Studio, use Node.js 22.13+ (22.x), 24.x, or 26+, and run:

```bash
cd axonx_studio
npm ci
npm run dev
```

Start the Python service separately as described in the [quick start](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart). See [Studio development](https://flowllm-ai.github.io/AxonX/en/development/studio) for proxy configuration. The documentation site requires Node.js 22+.

### Making a change

Reuse existing contracts and extension points. Keep research algorithms in Tasks/plugins, and preserve ownership and cleanup of asynchronous resources in the framework. Document intentional changes to CLI flags, API responses, configuration, task identity, and artifact formats.

Use temporary workspaces for tests. Do not commit `.env`, tokens, private data, runtime `.axonx/` contents, logs, or generated outputs. Ensure screenshots contain no credentials or private session content.

### Validation

Choose checks for the affected area and state the commands and results in your PR. For framework Python changes, run relevant tests first, then the framework suite as appropriate:

```bash
pytest tests/unit/<affected_test_file>.py
pytest tests
```

Both `pytest tests` and bare `pytest` exclude tests marked `integration`; the latter also collects factor and strategy plugin tests and requires their research dependencies. Run `pytest -m integration` only with the required credentials and services available, after reviewing the tests' external effects. Explain any checks you could not run.

For Studio changes, run from `axonx_studio/`:

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

Check relevant UI flows in English and Chinese, including empty data and request failures.

For documentation or theme changes, run from `github-pages/`:

```bash
npm ci && npm run build
```

The build verifies rendered pages and Markdown exports. Root and plugin READMEs and contribution guides are rendered from their canonical sources by the same build; update both languages together and verify example commands.

## 2. Contribute a Plugin

Use this path for research Tasks, factors, models, strategies, backtesting algorithms, and plugin configuration under `plugins/`. Reuse framework Tasks and extension points for new research capabilities; change `axonx/` when shared runtime capabilities are needed.

### Development setup

Create the Python environment and install the main package and development dependencies using the framework setup above, then install the plugins needed for your change in editable mode:

```bash
axonx plugin install -e ./plugins/qlib_a158
# Factor and strategy layers:
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

The repository's research plugins are not published to PyPI. Install the required plugins and their upstream dependencies in Alpha158 → factor → strategy order in the same Python environment. `-e` requires a source directory in the selected environment and cannot use `--output`. For remote deployment, build wheels, upload them with `POST /upload`, and pass the returned absolute `location` to `plugin install --target` in dependency order. Restart persistent services after Python source changes; reinstall after dependency or entry-point metadata changes.

The default pytest configuration includes factor and strategy plugin tests and all three plugin source paths. Install the research dependencies above when running those tests. See the [plugin guide](https://flowllm-ai.github.io/AxonX/en/plugins/management) for discovery and restart behavior.

### Making a change

Follow existing plugin layouts, the [Task development guide](https://flowllm-ai.github.io/AxonX/en/dev_guide), and the [plugin manifest contract](https://flowllm-ai.github.io/AxonX/en/reference/plugin-manifest). A new plugin should include package metadata, a plugin entry point and manifest, Task implementations, example configuration, tests, and English/Chinese READMEs.

Preserve task identity, lifecycle, configuration, and artifact compatibility; explain intentional changes in documentation and the PR. Update `tool.setuptools.package-data` for new runtime resources so wheels and sdists include them. Use temporary test workspaces and keep research data, credentials, and generated experiment outputs out of the repository.

### Develop with an Agent

External and built-in Agents can use the [AxonX Skill](skills/axonx/SKILL.md) and a research prompt to develop a new
plugin or improve an existing one. Provide a source checkout, file/command tools, and the selected execution service;
see [Agent integration](docs/en/agent/overview.md) for the two access paths. Keep plugin code changes, installation,
and experiment execution distinct, and apply the same contribution checks to Agent-authored code.

Use the adapted Qlib Alpha158 plugin as a reference implementation. Separate factor and strategy plugins can reuse compatible upstream code
and artifacts. For claimed improvements, record the code revision, data snapshot, training/evaluation windows,
parameters, costs, and Task IDs and start times; follow [experiment design](docs/en/research/experiments.md). Keep raw execution
records in the research environment and publish sanitized evidence and reproduction instructions.

### Validation

From the repository root, run the affected plugin tests first, for example:

```bash
pytest plugins/qlib_factor/tests
pytest plugins/qlib_strategy/tests
```

Choose commands for the plugins you changed; add relevant framework tests for framework interactions. Run `pytest` as appropriate after installing the research dependencies. Follow the integration-test requirements above for external services, and report dependencies, results, and skipped checks in the PR. Main-package releases do not publish research plugins; handle plugin packaging and publication separately.

## Shared requirements for both contribution paths

Before submitting, run `pre-commit run --files <changed-files>`, replacing the placeholder with the paths changed in your contribution. Documentation, PR, and release requirements follow.

Pre-commit organizes Python imports with Ruff before formatting with Black. Import rules live in `pyproject.toml`; only Ruff's `I` rules are enabled. Run `pre-commit run ruff-check --all-files` to organize imports across the repository. Review and stage any automatic fixes before committing.

## Documentation contributions

Edit the canonical guide under `docs/`, or the root/plugin README or contribution guide imported into the site, and update both languages together. Keep matching paths and shared assets under `docs/figures/`. Site navigation is defined in `docs/.vitepress/navigation.mjs`.

Do not edit `github-pages/.generated/` or `github-pages/dist/`; they are regenerated. For site development and deployment details, see [github-pages/README.md](github-pages/README.md). Keep the two root READMEs and contribution guides aligned when their instructions change.

## Submitting a pull request

Use a descriptive title; Conventional Commits such as `fix(tasks): preserve run status` or `docs: clarify quick start` are encouraged. Explain the problem, resulting behavior, compatibility impact, and validation. Include screenshots for visible UI changes and note any external-service tests that were skipped.

The PR template prompts for these details. List validation commands and results, explain any checks not run, and note English/Chinese documentation updates. Remove optional sections that do not apply.

Contributions are covered by the project's [Apache License 2.0](LICENSE).

## Releases

AxonX and Studio release independently. Commit version updates and pass the relevant CI before publishing. Integration tests require model API keys and run locally when needed.

- **AxonX**: update `axonx/_version.py`, then create and push `v<version>`. Publishing a GitHub Release for that tag automatically publishes `axonx` to PyPI. Alternatively, run `Release / AxonX Python package` manually with the version without `v`.
- **Studio**: synchronize `axonx_studio/pyproject.toml`, `package.json`, and `package-lock.json`, then push to `main`. Run `Release / AxonX Studio` manually with the `main` branch selected. Versions are read from the manifests; no tag or version input is required. The default `both` publishes PyPI before npm; `pypi` and `npm` publish independently. The npm tag is selected automatically: `latest` for stable versions and `next` for prereleases.

AxonX builds from its release tag; Studio builds from the exact `main` commit selected when the workflow starts. Both verify distribution versions. Studio's Python and npm packages contain identical static assets; Python prerelease metadata is normalized according to PEP 440. The AxonX release does not publish research plugins.

Package CI also checks that research-plugin wheels and sdists contain all Python modules and data files declared in `tool.setuptools.package-data`, with contents identical to the source tree. Update package-data declarations when adding runtime resources; declared patterns must match source files.

Configure PyPI Trusted Publishers for `axonx` and `axonx-studio` with their respective workflows and the `pypi` environment. Configure npm Trusted Publishing for `@flowllm-ai/axonx-studio` with `release-axonx-studio.yml` and the `npm` environment. A new npm package needs its initial publication before Trusted Publishing can be configured.

Existing versions fail publication rather than being overwritten or silently skipped. If npm fails during a dual release, rerun the failed job in the original workflow run to reuse the same artifacts. Single-package publishing is also available; keep the Studio sources unchanged when recovering through a new run. Do not move AxonX release tags.
