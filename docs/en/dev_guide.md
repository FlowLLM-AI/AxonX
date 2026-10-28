# AxonX Development and Operations Guide

AxonX runs quantitative research as typed Tasks and preserves execution evidence for CLI, HTTP, MCP and Studio. This document contains the setup, authoring, deployment, execution and inspection procedures needed to use it independently.

Work within the user's authorized scope. Examples alone do not authorize installation, execution, deletion, external messages or remote changes. Use discovered schemas and actual records; do not infer success from process creation or invent unavailable results.

## Environment and service

Use Python 3.12+ on macOS or Linux. Install the backend and prebuilt Studio, set a dedicated token, and start the foreground daemon/service:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install 'axonx[studio]'
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

Keep that terminal open; use another with the same environment and token. Open `http://127.0.0.1:1024/` and enter the token in Studio settings. Demo needs no market data or model credentials. `axonx` without the `studio` extra installs only the backend.

The startup logo and service console output appear in the foreground terminal and are retained in `workspace_dir/daemon/<identity>/service.log`, including across service restarts. Ctrl+C stops the daemon, service and service-owned manual CLI commands within a total limit of 5 seconds; already launched scheduled commands continue independently, while future schedule triggers stop.

For framework or plugin development, use a source checkout in an activated environment:

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e '.[dev,studio]'
```

Source paths below are relative to the checkout root. Service workspace paths belong to the selected execution machine. Package installation alone does not supply the example plugin sources.

CLI startup loads the nearest `.env` from the working directory or up to five parents, preserving existing environment values. Defaults are port `1024`, workspace `.axonx`, log directory `logs`, timezone `Asia/Shanghai`. To customize startup, save this as `app.yaml` and use `axonx app --config app.yaml` instead of the default startup command:

```yaml
extends: default
workspace_dir: .axonx
log_dir: logs
timezone: Asia/Shanghai
service:
  host: 127.0.0.1
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
cron: []
```

Configuration supports YAML/JSON, `${NAME}`/`${NAME:-default}` interpolation and `extends`. Mappings merge recursively; lists replace inherited lists. Relative runtime paths resolve from the process, not the configuration file. Restart the service after configuration changes.

## Discovery, connections and responses

Discover the selected environment before executing or installing:

```bash
axonx --help
axonx help
axonx help --job cli
axonx diagnose
axonx list_task_defs --include-schemas false
axonx get_task_def --task demo
axonx machine_status
axonx python --code 'print(1 + 2)' --timeout 30
```

`--help` is offline; `help` queries public Jobs. Bare `axonx exec` lists Tasks in the current interpreter; definition Jobs use the persistent service's startup catalog. `diagnose` reports build, Python, disk/resources and installed plugins, with credential-presence flags rather than secret values. Machine readings do not allocate resources automatically.

`python` runs short probes in a fresh service-interpreter process with its working directory and environment. Its execution timeout defaults to 30 seconds and is capped at 300; inspect `exit_code`, stdout/stderr and truncation flags. The process group is cleaned up when the request ends. Use Task execution/composition for long-running work.

Direct remote CLI needs no local service. Replace `node-b:1024`, configure its token, and use the same target for execution, status and artifacts:

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx version --target node-b:1024
axonx get_task_def --task demo --target node-b:1024
axonx exec --task demo --task-name remote-check --x 1 --y 2 --target node-b:1024
```

Addresses require an explicit port; HTTP(S) is accepted, with no credentials, subpaths or query strings. `--token` overrides environment credentials. Default local CLI uses `AXONX_SERVICE_TOKEN`; explicit `--target` uses `AXONX_TARGET_TOKEN`. Python clients receive tokens explicitly. Studio forwards through its backend's configured `targets` address/token entries.

HTTP uses Bearer authentication and `POST /jobs/NAME` with `arguments` and optional configured forwarding `target`. For example, send this body to `/jobs/cli`:

```json
{
  "arguments": {
    "argv": [
      "exec",
      "--task",
      "demo",
      "--task-name",
      "http-check",
      "--x",
      "1",
      "--y",
      "2"
    ]
  }
}
```

Ordinary responses are `{answer, success, metadata}`. A `cli` answer contains `stdout`, `stderr`, `exit_code`, `stdout_truncated` and `stderr_truncated`, retaining at most 1 MiB per channel. HTTP 200 and a successful status query do not establish Task success. CLI Job success/failure exits 0/1; invalid CLI inputs generally exit 2.

MCP uses Streamable HTTP at `/mcp`, exposes public Job names and schemas, and returns ordinary Job responses. Discover tools on the actual service. Without a service token, Jobs requiring authentication are omitted. Live events use `POST /jobs/NAME/events`: SSE kinds are `progress`, `log`, `artifact`, `agent_message`, `result`; only the terminal result establishes the Job outcome. Use `--stream true --stream-format json` for CLI event lines.

## Execution, identity and observation

Use `--field value` pairs: hyphens become underscores, dots create nested mappings, and values convert booleans, nulls, numbers and JSON. Quote Task IDs containing `#` and JSON arrays. Unknown Task inputs are rejected.

```bash
axonx exec --task demo --task-name check --x 1 --y 2
axonx status --task-id 'base#demo#check' --detail full
axonx wait_task --task-id 'base#demo#check' --client-timeout 600
axonx read_task_log --task-id 'base#demo#check' --offset -1 --limit 8192
axonx stream_task --task-id 'base#demo#check' --stream true
```

Local `exec` runs synchronously in the CLI process, prints business output (`result=3` here), and returns the Task exit code. It returns no submission handle. With an explicit target, the service's `cli` Job owns a child process group and streams output until exit. Native remote commands preserve the child exit status; negative signal codes map to `128 + signal`.

A Task ID is `task_type#registration#task_name`; types are `base`, `api`, `etl`, `analysis`, `train`, `predict`, `inference`, `backtest`. Instance names contain 1–32 letters, digits or hyphens; omitted names are generated. Metadata `started_at` distinguishes successive executions. States are `running`, `succeeded`, `failed`.

`status` and `wait_task` default to summaries in CLI; `--detail full` includes inputs, outputs, steps and children. `wait_task` captures the current start time and refuses a replacement during waiting. `read_task_log --started-at TIMESTAMP` guards a read; offsets are bytes and `next_offset` continues it. Lists/graphs use a periodically refreshed index (default 5 seconds); single-Task status reads metadata directly. `get_task_context` returns full selected metadata, paths and input relationships, not a byte-limited summary.

Execution configuration resolves as explicit CLI fields > service `get_config` > defaults. Shared fields are `workspace_dir`, `log_dir`, `timezone`, `execution_target`, `log_to_console`, `log_to_file`, `environment`; explicit environment keys merge. Only connection failures allow fallback. Authentication or invalid configuration fails. A workspace override affects that command; service queries still observe the service workspace. Default client timeout is 60 seconds; `--client-timeout` is separate from business deadlines.

After a command disconnect, inspect its Task record before retrying. Cancelling a remote command or shutting down its service can terminate its process group. Cancelling an observation stream does not terminate the observed Task.

## Author and package a Task

Create this minimal plugin; `__init__.py` can be empty:

```text
example/
  pyproject.toml
  example_plugin/
    __init__.py
    plugin.yaml
    task.py
```

Put the Task in `example_plugin/task.py`:

```python
from axonx.task.core.base import BaseTask
from axonx.task.models.params import BaseInputParams, BaseOutputParams

class AddInput(BaseInputParams):
    x: int
    y: int

class AddOutput(BaseOutputParams):
    total: int

class AddTask(BaseTask):
    """Add two integers and publish their sum."""
    input_cls = AddInput
    output_cls = AddOutput

    def build_task_steps(self):
        yield self.add

    def add(self):
        self.state["total"] = self.input_params.x + self.input_params.y

    def build_output_params(self):
        return AddOutput(total=self.state["total"])
```

Put registrations in `example_plugin/plugin.yaml`:

```yaml
tasks:
  example_add: example_plugin.task:AddTask
```

Save package metadata in `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=84.0.0"]
build-backend = "setuptools.build_meta"

[project]
name = "axonx-example"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["axonx>=0.3.0"]

[project.entry-points."axonx.plugins"]
example = "example_plugin"

[tool.setuptools.package-data]
example_plugin = ["plugin.yaml"]
```

From the directory containing `example/`:

```bash
axonx plugin install -e ./example
axonx exec --task example_add --task-name check --x 1 --y 2
```

The result is `total=3`. Distribution `axonx-example`, entry-point name `example`, and Task registration `example_add` serve different purposes. Registration names must be unique. Manifests accept only `tasks`; include runtime resources as package data. Application Components/Jobs use separate `Application(providers=...)` composition and configuration. A class docstring supplies the definition description.

`BaseTask` defaults to type `base`. Research subclasses select their corresponding types. Inputs/outputs derive from `BaseInputParams`/`BaseOutputParams` and reject undeclared fields. Yield synchronous callables; return an instance of `output_cls`, not a dictionary. `self.state` passes values between lazily generated steps. Use `self.task_dir` for outputs, `self.persistent_dir` for retained business state and `self.resolve_workspace_path()` for research input paths.

`TaskExecutor` owns preparation, identity, progress, metadata and terminal state. It calls `close()` after steps or initialization failure and builds final output after cleanup. Preserve data needed by the output builder. `report_progress()` updates the active step or named substeps; stop background producers before finishing. `publish_output()` persists a validated partial output, so its output builder must be repeatable. Atomic writes and snapshots live in `axonx.task.storage.files`.

Any Task can call `self.run_task("demo", node_name="add", x=1, y=2)` synchronously. `ChildTaskResult` exposes `success`, `child_task_id`, invocation `record`, typed `output_params` and JSON `output`; failed construction can leave ID/output unavailable. Children share process, workspace, timezone and business clock, and inherit the parent instance name unless `task_name` overrides it. `node_name` labels attempts, not directories. Repeated registration/name pairs replace finished outputs; consume or pin them first. Default `on_error="stop"` raises; `continue` permits later work but the default parent exit policy retains failure.

Declare input dependencies with a unique JSON array `upstream_task_ids`; CLI `exec` also accepts comma-separated IDs. Pass each child's dependencies explicitly. `get_task_graph` builds edges only from these input references; `missing` marks unavailable records and `provisional` marks existing records not yet `succeeded`. Parent/child calls are recorded separately in `parent_task_id`/`children`; neither containment nor invocation order adds an input edge or schedules a DAG.

## Install, deploy and refresh plugins

Install the reference plugins from the checkout in dependency order, selecting only the needed layers:

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
axonx plugin list
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
```

`plugin` without a target operates on the current Python environment; add a target to run in that service's interpreter. `show`/`uninstall` take a distribution or entry-point name; `inspect` also accepts a source directory or wheel. Source inspection/build produces wheel metadata without installation. Save the returned `wheel`, `sha256` and `content_sha256`; the two hashes identify wheel bytes and normalized content respectively.

Editable installation requires source on the executing machine and cannot combine with `--output`. Ordinary install builds a source tree or consumes an existing wheel, installs dependencies except AxonX itself, and validates installed provenance. Restart persistent services after installation or source changes; reinstall when dependencies/entry points change. New CLI processes rediscover plugins; existing processes are not version-isolated or automatically refreshed. Coordinate environment changes yourself.

`--target` interprets every native-command path on the target; it does not transfer local files. For local-to-remote deployment, build locally, upload to `/upload`, install absolute `location`, clean relative `path`, then restart and verify. Replace the actual wheel filename, address and token in this complete upload/install/cleanup example:

```python
import asyncio
import hashlib
import json
import os
from pathlib import Path
from axonx.client.http import HttpClient

async def deploy():
    wheel = Path("dist/plugins/ACTUAL_FILENAME.whl")
    expected = hashlib.sha256(wheel.read_bytes()).hexdigest()
    async with HttpClient(
        target="http://node-b:1024",
        token=os.environ["AXONX_TARGET_TOKEN"],
        timeout=600.0,
    ) as client:
        uploaded = await client.copy_file(wheel)
        try:
            response = await client.run_job("cli", {
                "argv": ["plugin", "install", uploaded.location],
            })
            result = response.answer
            if not response.success or result["exit_code"] != 0:
                raise RuntimeError(str(result))
            installed = json.loads(result["stdout"])
            if installed["sha256"] != expected:
                raise RuntimeError("Installed wheel differs from local wheel")
            print(installed)
        finally:
            await client.discard_file(uploaded.path)

asyncio.run(deploy())
```

`POST /upload` also accepts raw bytes with `x-file-name`, or multipart `file` plus optional `directory`; `x-file-directory` overrides the directory. Staging stays under workspace `tmp`. `StagedFile` contains relative `path`, absolute `location`, byte `size`; it carries no checksum. `DELETE /upload?path=...` performs cleanup. Default transfer budget is 512 MiB, with 64 KiB extra multipart framing. Cleanup does not roll back installation.

After install, request restart, wait for service reachability, inspect update completion, then query definitions:

```bash
axonx restart_service --target node-b:1024
axonx get_update_status --target node-b:1024
axonx list_task_defs --include-schemas false --target node-b:1024
axonx get_task_def --task qlib_a158_etl --target node-b:1024
```

Restart returns an accepted `update_id`; use it with `get_update_status --update-id ID` to track that operation rather than relying on the latest record. Installation failures or disconnects may leave partial environment changes; inspect installed metadata before retrying.

## Run and improve research

The reference chain is ETL → Train → Predict → Backtest. Factor analysis is an independent ETL downstream via `qlib_a158_factor`. Install `qlib_a158` first and prepare sufficient Tushare history. The data token is separate from the AxonX service token; optionally set `AXONX_TUSHARE_BASE_URL` for a compatible data service.

The commands below select one historical example window. Run each separately and check its exit code and full metadata before the next stage; scripts must stop on failure. Existing complete raw history can be reused instead of downloaded:

```bash
export AXONX_TUSHARE_TOKEN='replace-with-data-token'
axonx exec --task download_tushare_task --task-name data-01 \
  --start-date 20140101 --end-date 20240131
axonx exec --task qlib_a158_etl --task-name research-01 \
  --start-date 20150101 --end-date 20240131
axonx exec --task qlib_a158_train --task-name research-01 \
  --upstream-task-ids '["etl#qlib_a158_etl#research-01"]' \
  --train-start 20150101 --train-end 20230101
axonx exec --task qlib_a158_predict --task-name research-01 \
  --upstream-task-ids '["train#qlib_a158_train#research-01","etl#qlib_a158_etl#research-01"]' \
  --pred-start 20230101 --pred-end 20231231
axonx exec --task qlib_a158_backtest --task-name research-01 \
  --upstream-task-ids '["predict#qlib_a158_predict#research-01"]' \
  --top-ns '[20,30]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

Downloads write shared `tushare/` partitions outside the download Task directory. The default 7-day lookback is not enough for multi-year training or rolling features. Inspect coverage and raw-data permissions; empty/missing market data is not a valid zero return.

Training uses an exclusive end date and selects iterations on temporal validation before refitting. Prediction must start at or after training end, uses saved feature order and produces scores, not return forecasts. Do not join future labels into prediction or selection inputs.

Alternatively, run the installed parent Task, which owns child names and dependencies and returns `stage_task_ids`:

```bash
axonx exec --task qlib_a158_research --task-name pipeline-01 \
  --etl.start-date 20150101 --train.train-end 20230101 \
  --predict.pred-end 20231231 --analysis '{}'
```

Here `analysis: {}` enables factor analysis; omission disables it. Prediction start defaults to training end. Parent inputs reject caller-owned child names, dependencies and explicit backtest input files. Use leaf Tasks to reuse existing upstreams. Repeat remote research with the same target throughout; input paths and credentials belong to that machine.

Change only what the hypothesis requires: feature changes usually rerun ETL onward; model changes can reuse compatible ETL; portfolio changes can reuse compatible predictions. `qlib_factor` adds 13 optional features but training defaults to the 158 baseline; `qlib_strategy` reuses predictions with holding/rank/replacement policies. Lock data, labels, windows, training parameters, costs and universe definitions for controlled comparisons. Screen candidates in a development window and assess the locked choice on an independent confirmation window.

## Artifacts and research contracts

Research bases live in `axonx.task.core.research`; input/output models in `axonx.task.models.params`; portable protocols in `axonx.task.models.artifacts`. Custom Tasks may inherit `BaseTask` directly. Standard base outputs require:

| Stage    | Required base fields                                            |
| -------- | --------------------------------------------------------------- |
| ETL      | `rows`, `date_range`                                            |
| Analysis | `rows`; optional grouped `scores`                               |
| Train    | `train_rows`; optional metrics, parameters and `training_curve` |
| Predict  | `rows`, `date_range`, prediction `protocol`                     |
| Backtest | `default_universe`, nonempty `universes`, backtest `protocol`   |

`ArtifactRecord` is defined in `axonx.task.models.artifacts`; `artifact_record` and `verify_artifact` come from `axonx.task.storage.artifacts`. All outputs have `artifacts: dict[str, ArtifactRecord]`. Write files before publishing metadata. `artifact_record(path, task_dir)` records Task-relative `path`, byte `size`, `revision="<size>:<mtime_ns>"`. Call `verify_artifact(root, record)` to verify a regular file's size/revision; path resolution alone does not verify it. These revisions are not content hashes and cannot detect edits preserving size and mtime. Publish immutable files by atomic replacement; use real file-derived values.

`upstream_artifact(task, task_id, name)` requires a successful non-replica source and verifies an artifact. `pin_upstream_artifacts(task, task_id, *names)` snapshots verified files into the consumer's `inputs/`; `snapshot_model_collection()` verifies/copies a model collection. These helpers live in `axonx.task.storage.inputs`. Business compatibility and feature timing remain the consumer's responsibility.

Protocol headers require integer `version=1` and producer `task_type`; unsupported/missing headers are rejected. Qlib training registers `artifacts.model_manifest` pointing to `models.json`: `ModelCollection` contains `feature_protocol`, named `members` (`model_artifact`, `model`) and an artifact registry. A model manifest is a Qlib consumer requirement, not a mandatory `BaseTrainOutputParams` field. Feature semantics and fingerprints belong to the plugin.

`PredictionProtocol` requires nonempty `model_identity: dict[str, str]`, sorted unique `dates`, distinct nonempty member-to-column `score_columns` and `predictions_revision`. Qlib uses identity entries `models_sha256`/`features_sha256` and registers `artifacts.predictions`. Date ranges use `start`/`end`. Training curves use string `x` labels and finite, length-matched `y_left`/optional `y_right` series; a populated curve requires a left series and names cannot repeat across axes.

Stock ETL separates `dataset`, `labels`, `market`, `calendar`. Prediction rows require unique `(trade_date, trade_time, ts_code)` keys plus finite `pred`, Boolean `is_model_candidate`/`is_buyable_at_signal`, `signal_price`, `signal_adjustment_factor`. Predictions contain no future labels. The backtest also needs independent market/calendar artifacts; optional labels supply signal diagnostics. Pin input revisions before evaluation.

Stock backtest plugins inherit `axonx.task.builtins.stock.backtest.BaseStockBacktestTask`, implement `build_universes()` and `select_universe(signals, universe)` returning unique signal keys. Each universe publishes independent dates, dimensions, evaluation status and artifact-role references; daily/summary roles point into the root output artifact registry. `default_universe` selects one report. Publish `signals_format="stock-signals-v1"`; `signals.parquet` retains signals with `is_backtest_candidate`, `target_rank`, `label_return`. Actual fills, cash, positions, trades and orders are distinct from signal targets. Document execution/valuation timing, fees, missing-data handling and return units. Task success alone does not prove a complete or profitable evaluation.

## Workspace, reruns and cleanup

The directory rule is `<workspace>/<task_type>/<task_id>/`:

```text
.axonx/
  base/base#demo#check/
    metadata.json
    events.jsonl
    persistent/
  etl/etl#qlib_a158_etl#research-01/
  tushare/
  tmp/
  agent/
logs/
```

`metadata.json` stores the current identity, process ownership, lifecycle, input/output, steps and child invocations; `events.jsonl` records current progress events. `log_path` points to the actual text log, which may be outside the Task directory. Artifact paths are Task-relative; `preview_file` paths are workspace-relative.

```bash
axonx list_task_statuses --task-type etl --state succeeded
axonx get_task_graph --task-id 'base#demo#check'
axonx list_entries --path ''
axonx list_task_directories --task-type base
axonx preview_file --path 'base/base#demo#check/metadata.json' --max-bytes 8192
axonx kill --task-id 'base#demo#check' --timeout 5 --force false
axonx delete_entries --paths '["base/base#demo#check"]'
```

Treat kill and deletion as separate operations; the last command is a cleanup example for a verified stopped directory. `kill` checks machine/PID/process-start identity and resolves an in-process child to its root owner. `execution_target` advertises a reachable source service with an explicit port; loopback/wildcard addresses are rejected. It and source `workspace_dir` support remote termination; `machine_id` is an identity, not an address.

A same-name rerun first verifies the previous process has stopped, then replaces current files while retaining `persistent/`. There is no Task-directory coordination lock: serialize starts, deletion and replica replacement. Active, foreign or unverifiable running records block replacement. Queries do not settle stale records; runtime preparation or explicit kill can settle confirmed exited local processes. Deletion has no active-Task protection and removes retained data too.

Directory listings return at most 5000 sorted entries; continue from `offset + entries.length` when `truncated`. Row previews use `offset`, `limit`, `has_more` (server default 200 rows, maximum 5000; CLI default 20). Text/Markdown default to 512 KiB; JSON/YAML allow up to 32 MiB. CLI adds `max_bytes=8192`; partial JSON/YAML returns raw content with a parse error. JSONL has its own 512 KiB page budget. Inspect actual rows, parsing errors and truncation before drawing conclusions.

## Display synchronization and backups

Display synchronization copies bounded evidence, not executable environments. Ordinary selection includes terminal Tasks; `live_task_ids` optionally selects parent groups with exact child execution snapshots. `task_names` filters the final Task ID segment; an empty list includes all names. On the source, use this optional `sync.yaml` configuration with the actual destination and token:

```yaml
extends: default
targets:
  - address: http://node-b:1024
    token: ${AXONX_TARGET_TOKEN}
components:
  sync:
    default:
      backend: local
      target: http://node-b:1024
      task_index: default
      task_names: []
      live_task_ids: []
jobs:
  sync_flush:
    parameters: { type: object, properties: {}, additionalProperties: false }
    steps:
      - backend: sync_flush_step
        sync: default
```

Start with `axonx app --config sync.yaml`, then explicitly invoke `axonx sync_flush`. Default configuration leaves this Job disabled. The component reconciles changes, builds/uploads archives and applies `sync_tasks`; `task_sync_index` reports verified target snapshots. A prebuilt valid display archive can also be staged with `/upload` and passed as the relative `path` to `sync_tasks`, with optional Task-directory `deletions`.

Sender/receiver use the smaller transfer budget (default 512 MiB). Large date-keyed Parquet files may be sampled; omitted files are recorded in `replica.omitted`, retained files in `replica.files`. Live snapshots bind source, root Task/start time and ordered revision. Replicas cannot execute, be local kill targets or serve as research inputs; active original Tasks cannot be overwritten by sync.

For backup, stop/coordinate writers and retain complete Task directories, `persistent/`, raw data, external logs, Agent state, configuration, source/plugin versions and dependencies. Restoring files does not restore processes. Display replicas can omit inputs, models and raw data and are not a full backup.

## Scheduling and maintenance

To schedule local execution, save this as `scheduled.yaml` and start with `axonx app --config scheduled.yaml`:

```yaml
extends: default
timezone: Asia/Shanghai
cron:
  - expression: "0 16 * * 1-5"
    command: "axonx exec --task download_tushare_task --days-back 7"
```

Schedules accept exactly five numeric cron fields and local `axonx exec --task NAME` commands, parsed without a shell. Pipes, redirection and client options such as `--target` are unsupported. The application timezone controls triggers; missed slots are not replayed. An inherited list is replaced, and `cron: []` disables it. Restart to apply edits. There is no built-in skip/replace overlap policy; generated instance names keep distinct records, while fixed names require coordination.

The service computes triggers; the daemon owns launched scheduled commands. Service-owned manual CLI commands stop with the service, while daemon-owned scheduled executions survive service restart. The daemon does not resume or rerun completed Tasks. Inspect Task metadata and `logs/cron/entry-N.log` for outcomes.

```bash
axonx restart_service
axonx get_update_status
```

`restart_service` reloads configuration and loaded code. `update_from_git` fast-forwards the current branch, builds/installs AxonX and Studio, then replaces the service; `update_from_pip` upgrades published packages. Use one operation at a time. They require authenticated daemon-backed execution and accept no `force`. A response means acceptance; retain `update_id`, reconnect and call `get_update_status --update-id ID` until `succeeded` or `failed`. During maintenance new local work is rejected except version/update-status queries. Partial source/dependency changes are not rolled back. In-place updates do not freeze versions for running scheduled Tasks. Supervisor or startup-command changes require relaunching the whole daemon.

## Windows, online history and replay

`axonx.task.core.windows` provides `BaseWindowTask`, `BaseRealtimeApiTask`, `BaseInferenceTask`; inputs are `ExecutionWindow`/`WindowInputParams` in `models.params`, results are `WindowResult` in `models.reports`. Windows have unique keys, timezone-aware ordered start/end times and `end_at > start_at`.

Implement `execute_window(window, budget)` for generic windows; realtime collectors implement `collect(window, budget)` and return `None` to keep polling. Inference implements `initialize_run()`, `inputs_ready(window)` and `infer(window, budget)`, fixing one nonempty model-identity mapping at initialization. Release resources in `close()`. Each result is published with business state `done`, `skipped`, `incomplete` or `failed`, separate from Task state; incomplete/skipped windows do not fail the Task by default.

Use `DeadlineBudget.remaining_seconds`, `sleep()` and `check()` from `axonx.task.core.clock` to bound external timeouts, retries and publication. It cannot interrupt an arbitrary blocking operation. Exceptions retain earlier window results and stop the Task.

`axonx.task.storage.online.OnlineStore` publishes immutable role-based files under `persistent/online/commits/<commit_id>/` and atomically updates `manifest.json` in `persistent/online/`. Commits record Task/start identity, signal date/time, revision, model identity, protocol and artifact records. Strategy-identity changes require a new instance. Read full/frozen history with `read_online_history()` and verify/pin it with `pin_online_history()` before consuming; unreferenced files are not committed evidence.

`axonx.task.storage.replay.ReplayStream.create()` snapshots event files and publishes `stream.json` into a new directory, refusing overwrite; opening verifies referenced revisions. Inject `axonx.task.runtime.replay.ReplayClock` into a Task and use `ReplayCursor` to deliver events by timezone-aware `available_at`, strictly before deadlines. Only the creating thread advances replay time; lifecycle timestamps and performance measurements remain real.

## Built-in Agent sessions

External Agents use their host's model credentials and the CLI/MCP connection above. The default built-in backend uses the Claude Agent SDK. Configure its model environment on the service machine and restart:

```dotenv
CLAUDE_CODE_API_KEY=replace-with-model-key
CLAUDE_CODE_BASE_URL=https://api.anthropic.com
CLAUDE_CODE_MODEL_NAME=replace-with-model-name
```

Open Studio's Agent page or call:

```bash
axonx agent_chat --message 'List current workspace tasks and summarize their actual status.' --stream true --client-timeout 600
axonx list_agent_sessions --limit 20
```

Save `metadata.session_id` and pass `--session-id UUID` on later turns. `get_agent_session` reads history; `rename_agent_session`, `tag_agent_session`, `fork_agent_session`, `delete_agent_session` manage it. Running sessions cannot be deleted. `cancel_agent_turn --session-id UUID` interrupts that turn; use Task `kill` to stop an independent research execution. Closing a turn can also affect tools it owns.

The SDK `cwd` defaults to the workspace; set `components.agent.default.cwd` to an absolute checkout path for source work. Default `load_dev_guide=true` loads the bundled guide selected by application `language` (`en`/`zh`). `job_tools` is empty by default; configured names use an in-process Job bridge. SDK file/command tools and permissions remain separate; default `bypassPermissions` is not a read-only mode. AxonX owns session UUID/resume and serializes turns per session. Session storage is separate from Task artifacts and display sync.

## Verification and reporting

For source changes, run the affected tests in temporary workspaces; a basic framework check is `python -m pytest tests`, and a plugin check is `python -m pytest plugins/qlib_a158/tests`. Research tests need their installed dependencies; external-service tests require explicit preparation. Build/installation success does not prove an algorithm is correct.

For completed work, report the execution target/workspace, source/plugin versions or wheel hashes, Task IDs and `started_at`, terminal states, input revisions, artifacts, metrics and definitions. For performance claims, include data/window alignment, sample sizes, costs, missing-data effects and independent confirmation status. For failures or uncertain execution, report the actual error, completed stages and what remains unverified. Keep credentials and private data out of reports.
