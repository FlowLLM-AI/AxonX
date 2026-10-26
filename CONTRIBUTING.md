# Contributing to AxonX

English · [简体中文](CONTRIBUTING_ZH.md)

We welcome bug reports, feature requests, documentation improvements, research plugins, and code contributions.

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

| Module   | Allowed repository dependencies                                              | Public boundary                                                        |
| -------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `utils`  | None                                                                         | `env`, `logging` and `values`; environment loading is explicit         |
| `task`   | `utils.env`, `utils.logging`, `utils.values`                                 | Task authoring, data contracts, execution, storage and queries |
| `plugin` | Task authoring/data contracts and built-ins; shared utilities if needed      | Discovery, installation and `plugin.catalog` resolution                |
| `app`    | Task models and observation/storage APIs; shared utilities  | App-owned components, Jobs, transports and Workspace                   |
| `daemon` | Launcher: App and Task execution settings; supervisor: standard library only | Restart one application service and reap scheduled exec processes      |
| `cli`    | Other modules public entry points                                            | Parse arguments, route calls, render results and return exit codes     |

Task models and enums must not import execution, storage or plugin code. Task execution never imports App, Plugin or CLI. Plugin discovery lives in `axonx.plugin.catalog`; `TaskExecutor` receives a caller-supplied `resolve_task` callable. The Runner owns resolution and execution of composite children and binds an execution callback while the parent runs; Task classes do not import the Runner or retain a resolver.

`axonx/task/` contains only `__init__.py` and six capability packages:

| Package    | Responsibility                                                                                |
| ---------- | --------------------------------------------------------------------------------------------- |
| `models`   | Data contracts, enums, identity rules and parameter validation                                |
| `core`     | Task authoring bases, composition, execution windows and business clocks                      |
| `runtime`  | Execution, progress settlement, process identity/control, lifecycle reconciliation and replay |
| `storage`  | Workspace layout, metadata, event/log files, artifact snapshots, publication and history      |
| `query`    | Read-only summaries, dependency graphs, contexts and event/log streams                        |
| `builtins` | Concrete Tasks and domain implementations                                                     |

Runtime dependencies flow from `runtime` to `core`/`storage`/`models`, from `core` and `builtins` to `storage`/`models`, and from `query` to `storage`/`models`; built-ins also use authoring bases in `core`. Storage depends only on models within Task. The `DeadlineBudget` annotation in online storage is a type-only dependency on `core.clock`. Package initializers must not load unrelated execution capabilities. Use `task.models.identity` for enums and identity rules, and `task.models.base` for shared model policy and calendar-date validation. Process termination and stale-record settlement belong to `task.runtime.lifecycle`; storage only supplies the required reads and writes.

Task data contracts are organized by responsibility within `task.models`:

| Module      | Responsibility                                                                |
| ----------- | ----------------------------------------------------------------------------- |
| `base`      | Shared `TaskModel` policy and calendar-date validation                        |
| `identity`  | Task types, states, categories, naming and source Task IDs                    |
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

`task/core` contains six files. Import classes from their owning module:

| File           | Capability                                                                                                                             |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `task.py`      | `BaseTask` and synchronous `TaskStep`; validated inputs, identity, workspace paths, output and runtime callbacks                       |
| `composite.py` | `BaseCompositeTask`, `ChildTaskError`; synchronous children, invocation snapshots and failure policies                                 |
| `standard.py`  | ETL, Analysis, Train, Predict and Backtest bases, plus incremental `BasePredictionCompareTask` reports                                 |
| `windows.py`   | `BaseWindowTask`, `BaseRealtimeApiTask`, `BaseInferenceTask`; window scheduling, collection, fixed-model inference and partial results |
| `clock.py`     | Real business time (`WindowClock`) and monotonic deadlines (`DeadlineBudget`)                                                          |
| `__init__.py`  | Package documentation; import the owning modules as needed                                                                             |

Declare `input_cls` and `output_cls`, yield synchronous methods from `build_task_steps()`, and return the declared output model from `build_output_params()`. The step generator is lazy, so later branches can read `self.state` populated by earlier steps. Use `report_progress()` for progress. Release resources in `close()`, which the Runner also calls after failed initialization or rejected startup. Cleanup errors do not replace a primary failure. `on_failure(error)` records business details; the Runner owns lifecycle status. Output is built after cleanup, so retain the data needed to build it.

Composites call `run_task("registration", **inputs)` in their steps and consume `ChildTaskResult.output_params` or `.output` explicitly. Use ordinary Python conditions, loops and retries. The default policy stops on failure; `on_error="continue"` permits later children while keeping the parent failed. `children` exposes defensive snapshots. Children inherit the workspace, timezone, source and business clock.

Window inputs (`ExecutionWindow`, `WindowInputParams`) live in `models.params`; `WindowResult` lives in `models.reports` with training curves and prediction comparison details. Implement `execute_window(window, budget)` for a generic window Task, or `collect(window, budget)` for realtime collection; returning `None` from the collector polls again within the budget. Inference implements `initialize_run()`, `inputs_ready(window)` and `infer(window, budget)`, setting one nonempty `model_identity` during initialization. Extend `validate_run()`, `window_skip_reason(window)` and `window_output()` for validation, business exclusions and extra output. Release resources through the same `close()` hook.

Windows execute in start order and publish each outcome, including missed windows, input timeouts and deadline overruns. Exceptions retain earlier results and stop the Task. Business outcomes `incomplete` and `skipped` do not fail the Task by default. An uncommitted result returned after the deadline becomes incomplete; committed results are checked against their recorded in-window commit time. Bound requests and retries by `budget.remaining_seconds`, wait with `budget.sleep()`, and call `budget.check()` before publication. A budget cannot forcibly interrupt a blocking request.

Import `ReplayClock` from `task.runtime.replay` and pass `clock=ReplayClock(aware_datetime)` to replay business time; the default clock uses real time. Creation, lifecycle timestamps and performance measurements remain real. Only the thread creating a replay clock may advance it. Deadlines and window ordering compare UTC instants, including repeated local times during daylight-saving transitions.

Invocation identity and child results are `models.lifecycle.TaskContext` and `ChildTaskResult`; the context contains no logger or service handles. The Task retains its logger. Migration: prediction comparisons moved from `core.compare` to `core.standard`; realtime and inference bases moved from `core.realtime` and `core.inference` to `core.windows`. The internal `_WindowTask` is now public `BaseWindowTask`, and window cleanup uses `close()` instead of `close_run()`. Removed paths have no compatibility modules.

Resident components stay in App: `components/task_index` owns polling, caching and subscriptions, `components/sync` owns replica preparation, transfer, indexing and application, and `components/updater` owns application admission and response completion. App uses public `task.query` observation APIs and the Task storage capabilities it needs; it never loads Task execution or research plugins. Observation leaves Task records unchanged; startup and explicit termination can settle confirmed exited local processes. Receiving archives and querying replica indexes work without a configured outbound sync component or target. CLI contains no resident components or Steps.

App owns configuration, registry, async helpers, Workspace and the startup banner. Workspace provides file operations without Task-specific hiding or deletion policy. The configured `command` vector supplies the external command driver; an injected update backend owns prepare/commit/status. `daemon.launcher` creates one Application with explicit `task.runtime.settings.ExecutionSettings`. Its `components/cron` component reads `app/crontabs/*.cron` or an explicit `--cron` source on startup and awaits an injected launch callback. CLI supplies command validation; the launcher validates the entire file before starting the daemon. `--config` and `--cron` are parsed separately. Restart to apply schedule edits; missed slots are not replayed.

The daemon supervises only the application service. Manual CLI children stop with that service; their execution never delays a restart beyond the cleanup deadline. Scheduled exec processes are created and reaped by the daemon and run to completion across service restarts. Updates reject new scheduled launches, stop the service and manual children, run the updater, then start a fresh service that rereads both configuration sources. In-place updates do not freeze code or dependencies for existing Tasks. `daemon.worker` uses only the standard library and receives complete command, working-directory, environment and log-file values; it does not interpret crontabs or restart completed Tasks.

Application YAML/JSON loading, inheritance and merging belong to `app/config`. Environment loading and interpolation live in `utils/env.py`; scalar conversion is shared through `utils/values.py`. Log configuration, retention and argument formatting live in `utils/logging.py`; App owns the cleanup schedule, and Task owns execution log scopes and log reading. Crontab lookup, loading and parsing belong to `app/crontabs`, alongside the bundled `.cron` files; `components/cron` owns only scheduling and lifecycle. Both loaders reuse `app/config/locator.py`. Command-line option grammar belongs to CLI. Workspace operations return their models from `app.workspace.models` directly: `WorkspaceListing`, concrete `FilePreview` variants, `DeletedEntry` and `StagedFile`. Entry filters receive `WorkspaceEntry` objects. Job and HTTP adapters use those results directly and serialize them at the transport boundary.

Task owns atomic writes, revisions and snapshots in `task.storage.files`, online publication locking in `task.storage.locking`, and exact process inspection in `task.runtime.process`. Plugin owns its checksums. App keeps the small atomic write needed for upload staging. Task metadata has no coordination lock; callers serialize competing mutations of the same Task directory. Preserve online publication consistency and Daemon's singleton lock. These module moves have no compatibility imports.

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
