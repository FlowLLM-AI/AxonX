# Workspace and Persistent Records

The workspace stores task status, successful results, and research artifacts, providing the shared data source for Studio and task queries. Its default root is `.axonx` under the startup directory. The built-in default configuration accepts `AXONX_WORKSPACE_DIR` from the shell or `.env`; an explicit `workspace_dir` configuration or `--workspace-dir` CLI option can also select the root. The log directory is configured separately and defaults to `logs`.

![Task records, artifact readers and bounded display replicas](../../figures/concepts/workspace.svg)

## Directory Layout

The following shows runtime data under the default configuration. Directories are created on demand; `<...>` denotes an actual identifier, and plugin artifacts depend on the Task.

```text
<workspace_dir>/                         # Defaults to .axonx/
├── tasks/                               # Tasks with fixed names
│   └── <task_type>/<task_id>/
│       ├── metadata.json                # Authoritative current execution record
│       ├── events.jsonl                 # Progress events
│       ├── task.log                     # Written when file logging is enabled
│       ├── persistent/                  # Execution history and cumulative data retained on rerun
│       └── ...                          # Plugin models, reports and comparisons
├── tmp/
│   ├── tasks/<task_type>/<task_id>/      # Generated names; same Task contents
│   ├── uploads/<upload_id>/<file>        # Upload staging
│   ├── sync/
│   │   ├── send-<operation_id>/          # Outgoing sync staging
│   │   └── receive-<operation_id>/       # Incoming validation and replacement staging
│   └── plugins/<source_fingerprint>/
│       ├── <plugin>.whl                 # Rebuildable wheel cache
│       └── .build.lock                  # Concurrent build lock
├── tushare/                             # Shared raw data, separate from collection Tasks
│   ├── stock_basic.parquet
│   ├── namechange.parquet
│   ├── trade_cal.parquet
│   └── <YYYY>/<YYYYMMDD>/
│       ├── daily.parquet
│       ├── adj_factor.parquet
│       ├── stk_limit.parquet
│       └── index_weight.parquet
├── daemon/<service_id>/                  # Per-service supervisor state
│   ├── daemon.lock
│   ├── plan.json
│   ├── processes.json
│   ├── service.log                      # Service process console output
│   ├── supervisor.py
│   ├── update.py
│   └── updates/<update_id>/
│       ├── plan.json
│       ├── record.json
│       ├── update.py
│       └── update.log
└── agent/
    ├── claude/<component_name>/          # Claude SDK configuration and runtime state
    └── session-store/<project_key>/<session_id>/
        ├── transcript.jsonl
        ├── summary.json
        └── <subpath>.jsonl               # Optional child session records

<log_dir>/                               # Configured separately; defaults to logs/
├── YYYY-MM-DD_HH-MM-SS_<pid>.log          # Service/startup logs, plus rotated files
└── cron/entry-<index>.log                 # Scheduled process console output
```

`workspace_dir` and `log_dir` are resolved independently; `logs/` is not inside `.axonx/` by default. Agent state and session paths are configurable, and plugin builds accept `--output` for another output directory. The tree shows default locations. The daemon's local communication socket lives in the system temporary directory, outside the workspace.

Fixed names use `tasks/<task_type>/<task_id>/`. The reserved generated format is `YYYYMMDDHH` plus four alphanumeric characters; matching names use `tmp/tasks/<task_type>/<task_id>/`, including names inherited by children. Task IDs remain `<type>#<registration>#<name>`. New generated roots never replace an existing directory; child retries may reuse the same directory owned by their parent. The type enumeration is base/api/etl/analysis/train/predict/inference/backtest.

For example, a fixed-name training Task uses `tasks/train/train#qlib_a158_train#baseline/`, while a generated one uses `tmp/tasks/train/train#qlib_a158_train#2026102912aB3d/`. Classification depends only on the final name, without an additional storage-category field. Parameter comparisons are ordinary analysis Tasks, with `summary.csv` and `comparison.json` inside their Task directory.

The reserved `persistent/` directory holds Task-owned cumulative business data. Same-name reruns retain it and clear all other run-owned files; explicit Task deletion removes it, and display synchronization replaces the target directory with selected published outputs. The framework owns `persistent/task.lock` and `persistent/runs.jsonl`; the existing `TaskJournal` appends started/finished execution metadata; a replacement start records `previous_started_at`. Plugins own other business files and must not overwrite this journal. It must be a regular directory, not a symbolic link.

## Runtime Records

| File                    | Lifecycle                                                      | Contents                                                                                                             |
| ----------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `metadata.json`         | Execution startup through terminal state                       | Task ID, started_at, process identity, input/output, state, steps, error, exit code, log path, and child invocations |
| `persistent/runs.jsonl` | Appended at execution start and finish, retained across reruns | Event, complete execution metadata and the previous execution start time                                             |
| `events.jsonl`          | Appended as the executor reports progress                      | Replayable progress events, one JSON object per line                                                                 |

One atomic metadata snapshot is the authoritative Task record. `TaskExecutor` updates it in the synchronous execution process, including child invocations, cleanup and final output. Runtime preparation and explicit `kill` can reconcile confirmed dead local processes; queries only observe files. Each rerun replaces `metadata.json` and `events.jsonl`; neither file is an archive of previous executions.

Child invocations are recorded in `metadata.json.children`; child directories remain under their own type directories, rather than below the parent. Workflow synchronization selects available matching child executions; deleting a parent does not automatically delete children.

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
tasks/etl/etl#my-etl#dataset-01/data/dataset.parquet
```

Do not treat an artifact's path as relative to the workspace root, or use absolute paths or `../` to escape the task directory. Production plugins should record size and revision after writing the file.

## Where Logs Are Stored

When file logging is enabled, `status.log_path` is `task.log`, relative to the Task directory. The file captures that Task and nested child logs while excluding siblings. Read it through `read_task_log` or Studio. Logs follow the current execution: an allowed same-name rerun replaces them, and deleting the Task removes them. They are not subject to service-log expiry.

`events.jsonl` is the progress journal. `log_dir` separately holds service/startup logs, excluding Task-scoped messages. Scheduled processes suppress console logging by default so cron output does not duplicate Task logs; an explicit `--log-to-console true` overrides that choice.

## Indexes and Files

TaskIndex polls metadata under type directories (every 5 seconds by default), maintaining one snapshot for lists and dependency graphs. Single-Task status, waiting and streaming read current metadata directly. Restarting can rebuild indexes from valid files; it does not retrain models or download raw data for you.

Task lists include every valid lifecycle record. Studio research pages select records with `state=succeeded`; the existence of metadata alone does not mean an experiment succeeded.

## Browse directories

```bash
axonx list_entries --path ''
axonx list_task_directories --path tasks/base
axonx preview_file --path 'tasks/base/base#demo#check/metadata.json' --max-bytes 8192
```

Paths are relative to the selected service workspace. `tmp/uploads/` expiry only visits uploads, never temporary Tasks, sync files or plugin wheels. Sync staging is removed at the end of its operation; temporary Tasks and caches have no automatic expiry. list_entries uses offset pagination and bounded listings. list_task_directories selects type directories containing metadata.json, regardless of current lifecycle state. The Task ID includes # and should be shell-quoted.

## Preview records and artifacts

Use paths from current metadata.output_params.artifacts and resolve them inside the Task directory. Preview text, Markdown, JSON/YAML, CSV, JSONL and Parquet through preview_file. Structured previews and row pages have format-specific fields; inspect parse errors, truncation, row_count and has_more rather than assuming every file returns the same shape.

## Formats and limits

`max_bytes` controls text, Markdown, JSON and YAML previews (up to 32 MiB); `offset` and `limit` page row formats, with at most 5000 rows. JSONL has its own 512 KiB page budget; `max_bytes` does not change it. CLI defaults are 20 rows/8192 bytes. JSONL retains malformed/incomplete lines with raw content and parse_error; valid rows include parsed data. A bounded preview is not a full artifact or a research-quality acceptance check.

## Clean up files and directories

| Path           | Purpose and cleanup rules                                                                                                                                      |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tushare/`     | Shared raw data; retain it when cleaning Tasks. Collection records and raw data are stored separately, so deleting a collection Task does not delete raw data. |
| `tasks/`       | Review names before deletion and check downstream dependencies. Deleting a parent does not cascade to children.                                                |
| `tmp/tasks/`   | Temporary Tasks collected in one location; remove completed Tasks once no longer needed by consumers. No automatic expiry.                                     |
| `tmp/uploads/` | Upload staging; subsequent uploads clean files older than the default 7 days. Callers can also delete them explicitly.                                         |
| `tmp/sync/`    | Removed when an operation ends. Confirm synchronization has stopped before deleting leftovers from an abnormal exit.                                           |
| `tmp/plugins/` | Rebuildable cache; remove when no build or installation is using it. This does not uninstall plugins from the Python environment.                              |
| `daemon/`      | Service state and update records; running services still need these files. Review directories of retired services before removal.                              |
| `agent/`       | Agent configuration, state and session history; retain according to session recovery needs.                                                                    |
| `log_dir`      | Timestamped logs follow a 7-day retention policy. Cron output and logs inside daemon directories are separate from Task logs.                                  |

Use delete_entries with a JSON paths array. This general file capability has no active-Task process protection. Stop writers, check source identity and serialize against execution before deleting current Task directories. Deletion removes persistent/ too; it does not terminate a process or rebuild downstream outputs.

## Upload and subsequent consumption

POST /upload or HttpClient.copy_file stages one file under `tmp/uploads/`. StagedFile contains path, size and absolute location. Install a target-side plugin using location; sync and cleanup use relative path. Uploading does not install anything, and plugin installation does not delete the upload automatically. Clean up in finally; see [Upload API](../api/workspace.md).

See [operations and recovery](../guides/operations.md#backup-and-recovery) for consistent backups; display replicas omit data and cannot replace them.

[Task contracts](../reference/task-contracts.md) · [Research artifacts](../reference/research-artifacts.md) · [Workspace API](../api/workspace.md)
