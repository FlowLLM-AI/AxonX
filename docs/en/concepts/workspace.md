# Workspace and Persistent Records

The workspace stores task status, successful results, and research artifacts, providing the shared data source for Studio and task queries. Its default root is `.axonx` under the startup directory. The built-in default configuration accepts `AXONX_WORKSPACE_DIR` from the shell or `.env`; an explicit `workspace_dir` configuration or `--workspace-dir` CLI option can also select the root. The log directory is configured separately and defaults to `logs`.

![Workspace file responsibilities](../../figures/concepts/workspace.svg)

## Shared Python Workspace

`axonx.common.workspace.Workspace` is the shared filesystem entry point for App, Task, CLI, Cron, and Task archive application. Constructing it normalizes the root without creating directories. `ApplicationContext` owns one instance, exposed as `app.workspace` and `self.workspace` on application components and Steps. Tasks expose their own instance rooted at the same configured workspace. Existing `workspace_path` properties remain available.

The implementation is grouped under `axonx/common/workspace/`: `core.py` provides file operations, `preview.py` handles file formats, and `models.py` defines shared result schemas. Import `Workspace` from the package; import result schemas explicitly from `axonx.common.workspace.models`. The base import does not load Pydantic or optional format libraries. App owns Job/HTTP adapters; Task retains metadata and execution policies.

```python
from axonx.common.workspace import Workspace

workspace = Workspace(".axonx", transfer_budget_bytes=512 * 1024 * 1024)
workspace.ensure()  # Explicit creation; construction itself is read-only.
listing = workspace.list_entries("", offset=0)
staged = workspace.stage_bytes(b"hello", "note.txt")
preview = workspace.preview_file(staged["path"])
workspace.discard_staged(staged["path"])
```

| Requirement                                                         | Shared mechanism                                                                          | Caller-owned rules                                                                                                                                          |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Root initialization, subprocess working directories and environment | `root`, `ensure()`                                                                        | App startup and Cron launch configuration                                                                                                                   |
| Untrusted relative paths                                            | `resolve()`, `resolve_file()`, `resolve_directory()`, `resolve_deletable()`, `relative()` | Refuse absolute paths, parent traversal, symlinks, and root deletion                                                                                        |
| Configured Agent paths and research inputs                          | `locate()`                                                                                | Confined by default; Task inputs explicitly use `external=True` to retain support for external files                                                        |
| Directory browsing and Task Run listing                             | `list_entries(path, offset=..., include=...)`                                             | Optional root-level hidden names and a filter applied before pagination                                                                                     |
| Bounded format previews                                             | `preview_file(path, offset=..., limit=..., max_bytes=...)`                                | App validates the returned data against its response models                                                                                                 |
| Batch deletion                                                      | `delete_entries(paths)`                                                                   | Validate all selections and deduplicate parent/child paths before mutation; an optional `before_delete(root, targets)` callback protects domain-owned files |
| Uploads and synchronization input staging                           | `stage_bytes()`, `stage_stream()`, `staged_file()`, `discard_staged()`                    | App supplies its transfer budget and uses the default `tmp/` staging directory                                                                              |

Workspace returns plain dictionaries and lists. It imports neither application schemas nor Task code; format libraries are loaded only when needed. Its optional transfer budget is unlimited when omitted, while the application always supplies its configured budget. The application also supplies `.task-records` visibility and Task deletion protection from `task/storage/records.py`.

Task identity/layout, metadata transactions and reconciliation, event/log readers, artifact validation, persistent storage and display-replica synchronization remain in `task/`. They use the shared filesystem mechanism without moving their lifecycle or schema rules into Common. Standalone daemon workers retain standard-library-only path handling. The old `ConfinedPaths`, `WorkspacePaths`, `StagedFiles`, and application workspace operation functions are removed; Python callers use `Workspace` methods. CLI/HTTP responses and persisted formats are unchanged.

## Directory Layout

The following illustrates a demo and a research plugin task; plugin filenames depend on actual artifacts:

```text
.axonx/
  base/
    base#demo#trial-01/
      metadata.json
      events.jsonl
  etl/
    etl#my-etl#dataset-01/
      metadata.json
      events.jsonl
      dataset.parquet
  train/
  predict/
  backtest/
  analysis/
  inference/
  tushare/                       # Raw data written by data download tasks
  plugins/artifacts/             # Default CLI wheel build cache
  agent/                         # Session data under the default Agent configuration
logs/                            # Separate log directory, not necessarily inside the workspace
```

The directory rule is `<task_type>/<task_id>`, rather than `<task_type>/<registered_name>/<run_id>`. Task type directories come from the enumeration; a directory's existence does not mean its algorithm plugin is installed.

The reserved `persistent/` directory holds Task-owned cumulative business data. Same-name reruns retain it and clear all other run-owned files; explicit Task deletion removes it, and display synchronization replaces the target directory with selected published outputs. Plugins own its schema, updates, and locking. It must be a regular directory, not a symbolic link.

## Runtime Records

| File            | Lifecycle                               | Contents                                                                                        |
| --------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `metadata.json` | Acceptance through every terminal state | Identity, Run ID, input/output, state, steps, error, exit code, log path, and child invocations |
| `events.jsonl`  | Appended as the worker reports progress | Replayable progress events, one JSON object per line                                            |

One atomic metadata snapshot is the authoritative Task record. The Runner owns updates during execution; Task record reconciliation settles unfinished records only after confirming the original local process has stopped. There are no separate status or composition documents, no duplicate result envelopes, and no legacy-format fallback.

Child invocations are recorded in `metadata.json.children`; child directories remain under their own type directories, rather than below the parent. Synchronizing or deleting a parent does not include its children automatically.

Readers treat malformed, unsafe, or identity-mismatched records as missing. They never read FIFOs or follow symbolic links. Transient I/O errors can be retried by lifecycle operations.

## Relative Artifact Paths

A research Task's `output_params.artifacts` can record artifacts:

```json
{
  "artifacts": {
    "dataset": {
      "path": "data/dataset.parquet",
      "size": 10240,
      "revision": "<size>:<mtime_ns>"
    }
  }
}
```

Here, path is relative to the Task directory. The workspace preview path is therefore:

```text
etl/etl#my-etl#dataset-01/data/dataset.parquet
```

Do not treat an artifact's path as relative to the workspace root, or use absolute paths or `../` to escape the task directory. Production plugins should record size and revision after writing the file.

## Where Logs Are Stored

`status.log_path` records the actual log location. The logging system is controlled by `log_dir`; Task logs are not guaranteed to live inside task directories. Read them through `read_task_log` or Studio task details rather than guessing `<task_dir>/log.txt`.

`events.jsonl` is a progress event log, distinct from Python text logs. Backing up task directories preserves progress events; text logs in an external directory need a separate backup.

## Indexes and Files

TaskRepository scans and watches only metadata under type directories, maintaining one index for task queries. Restarting can rebuild indexes from valid files; it does not retrain models or download raw data for you.

Task lists include every valid lifecycle record. Studio research pages select records with `state=succeeded`; the existence of metadata alone does not mean an experiment succeeded.

## Backup Scope

To reproduce experiments, retain task directories, raw data, service configuration, plugin versions, and model dependencies. Preserve Agent sessions, logs, and plugin source separately according to actual usage.

Copying the entire workspace after stopping writes is the easiest way to obtain consistent files. Task synchronization copies only terminal Task directories and cannot replace a complete backup of raw data, Agent sessions, logs, and the software environment.

Rerunning a fixed name replaces the old directory. Deleting upstream directories creates missing nodes in downstream lineage and may prevent downstream reruns from reading original artifacts.

## Related Documentation

[Workspace Browsing](../guides/workspace-files.md) · [Task Contracts](../reference/task-contracts.md) · [Research Artifacts](../reference/research-artifacts.md) · [Backup and Recovery](../guides/operations.md)

Source: [Workspace layout](../../../axonx/task/storage/workspace.py), [Metadata](../../../axonx/task/storage/workspace.py), [Artifact paths](../../../axonx/task/storage/artifacts.py).
