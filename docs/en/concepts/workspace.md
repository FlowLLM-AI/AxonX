# Workspace and Persistent Records

The workspace stores task status, successful results, and research artifacts, providing the shared data source for Studio and task queries. Its default root is `.axonx` under the startup directory. The built-in default configuration accepts `AXONX_WORKSPACE_DIR` from the shell or `.env`; an explicit `workspace_dir` configuration or `--workspace-dir` CLI option can also select the root. The log directory is configured separately and defaults to `logs`.

![Task records, artifact readers and bounded display replicas](../../figures/concepts/workspace.svg)

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

The directory rule is `<task_type>/<task_id>`, rather than `<task_type>/<registered_name>/<started_at>`. Task type directories come from the enumeration; a directory's existence does not mean its algorithm plugin is installed.

The reserved `persistent/` directory holds Task-owned cumulative business data. Same-name reruns retain it and clear all other run-owned files; explicit Task deletion removes it, and display synchronization replaces the target directory with selected published outputs. Plugins own its schema, updates, and locking. It must be a regular directory, not a symbolic link.

## Runtime Records

| File            | Lifecycle                                 | Contents                                                                                                             |
| --------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `metadata.json` | Execution startup through terminal state  | Task ID, started_at, process identity, input/output, state, steps, error, exit code, log path, and child invocations |
| `events.jsonl`  | Appended as the executor reports progress | Replayable progress events, one JSON object per line                                                                 |

One atomic metadata snapshot is the authoritative Task record. `TaskExecutor` updates it in the synchronous execution process, including child invocations, cleanup and final output. Runtime preparation and explicit `kill` can reconcile confirmed dead local processes; queries only observe files. Each rerun replaces `metadata.json` and `events.jsonl`; neither file is an archive of previous executions.

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

TaskIndex polls metadata under type directories (every 5 seconds by default), maintaining one snapshot for lists and dependency graphs. Single-Task status, waiting and streaming read current metadata directly. Restarting can rebuild indexes from valid files; it does not retrain models or download raw data for you.

Task lists include every valid lifecycle record. Studio research pages select records with `state=succeeded`; the existence of metadata alone does not mean an experiment succeeded.

## Browse directories

```bash
axonx list_entries --path ''
axonx list_task_directories --task-type base
axonx preview_file --path 'base/base#demo#check/metadata.json' --max-bytes 8192
```

Paths are relative to the selected service workspace. list_entries uses offset pagination and bounded listings. list_task_directories selects type directories containing metadata.json, regardless of current lifecycle state. The Task ID includes # and should be shell-quoted.

## Preview records and artifacts

Use paths from current metadata.output_params.artifacts and resolve them inside the Task directory. Preview text, Markdown, JSON/YAML, CSV, JSONL and Parquet through preview_file. Structured previews and row pages have format-specific fields; inspect parse errors, truncation, row_count and has_more rather than assuming every file returns the same shape.

## Formats and limits

`max_bytes` controls text, Markdown, JSON and YAML previews (up to 32 MiB); `offset` and `limit` page row formats, with at most 5000 rows. JSONL has its own 512 KiB page budget; `max_bytes` does not change it. CLI defaults are 20 rows/8192 bytes. JSONL retains malformed/incomplete lines with raw content and parse_error; valid rows include parsed data. A bounded preview is not a full artifact or a research-quality acceptance check.

## Clean up files and directories

Use delete_entries with a JSON paths array. This general file capability has no active-Task process protection. Stop writers, check source identity and serialize against execution before deleting current Task directories. Deletion removes persistent/ too; it does not terminate a process or rebuild downstream outputs.

## Upload and subsequent consumption

POST /upload or HttpClient.copy_file stages one file under tmp. StagedFile contains path, size and absolute location. Install a target-side plugin using location; sync and cleanup use relative path. Uploading does not install anything, and plugin installation does not delete the upload automatically. Clean up in finally; see [Upload API](../api/workspace.md).

See [operations and recovery](../guides/operations.md#backup-and-recovery) for consistent backups; display replicas omit data and cannot replace them.

[Task contracts](../reference/task-contracts.md) · [Research artifacts](../reference/research-artifacts.md) · [Workspace API](../api/workspace.md)
