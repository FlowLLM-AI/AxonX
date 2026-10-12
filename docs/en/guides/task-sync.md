# Task snapshot synchronization

Task synchronization copies complete terminal Task directories from a source to a target. On every source startup, it reads the target's `task_sync_index`, scans local terminal directories, and queues missing or different snapshots. There is no persisted acknowledgement or failed-transfer state.

## Scope and lifecycle

`task_names` matches the last segment of `<task type>#<registration>#<task name>`, across all task types and registrations. An empty list includes every name. Startup comparison uses SHA256 content digests of file names and contents, including metadata, events, and artifacts. This detects named-task reruns and artifact changes even when the Task ID is unchanged. Hashing reads the matching snapshots on both machines; large workspaces take longer to reconcile.

During operation, Repository changes are coalesced by Task ID. Only terminal snapshots are sent; queued/running tasks are skipped until a later completion change. A watcher recovery reconciles the indexes again to recover missed changes. Local deletion is ignored and does not delete target records.

Snapshots exclude workspace-wide Tushare raw data, Agent sessions, external logs, and plugin environments. They do not migrate workers or automatically copy dependencies with other task names. Target reruns still require plugins, data, and an execution environment.

## Target setup

Both services need the updated AxonX default configuration with `task_sync_index`, `sync_tasks`, and `/files`. An older receiver without the index Job cannot participate in startup reconciliation. A target does not need the sender-side sync component.

```bash
export AXONX_SERVICE_TOKEN='<receiver token>'
axonx start --service.host 0.0.0.0 --service.port 1024
```

## Source configuration

```yaml
extends: default
targets:
  - address: http://archive.example:1024
    token: ${AXONX_SYNC_REMOTE_TOKEN}
components:
  sync:
    default:
      backend: local
      task_repository: default
      target: http://archive.example:1024
      task_names: [research-model]
      max_archives_per_flush: 4
      max_file_bytes: 104857600
      max_archive_bytes: 268435456
      timeout_seconds: 300
jobs:
  sync_flush:
    enable_serve: false
    steps:
      - backend: sync_flush_step
        sync: default
schedules:
  workspace_sync:
    job: sync_flush
    cron: "* * * * *"
    concurrency_policy: forbid
```

```bash
export AXONX_SYNC_REMOTE_TOKEN='<receiver token>'
axonx start --config sync-source.yaml
```

The component's target must match a configured address. For multiple destinations, configure one sync component and one independently scheduled flush Job per destination. Names sent to the same destination can share a component and archive batches.

`task_ids`, `task_id_prefixes`, and `sync_on_start` have been removed and are rejected. Replace identity filters with `task_names`; startup reconciliation is always performed. Old workspace `sync/*.json` state files are ignored and may be removed manually.

## Batching, failures, and budgets

Multiple complete Tasks are packed into one archive, and the HTTP connection is reused throughout a flush. The per-file limit defaults to 100 MiB, the archive budget to 256 MiB, and the per-flush archive count to four. A Task must fit in one archive; large Tasks are not split. `max_archive_bytes` must exceed `max_file_bytes` and must respect the receiver's 256 MiB upload limit.

`SyncReport` includes `uploaded`, `rejected`, `oversized`, `deferred`, and `archives`. `archives` counts attempted batches. Deferred Tasks have not been attempted and remain in the memory queue for the next scheduled flush. Oversized or incomplete snapshots are logged and dropped from that queue.

Each batch is attempted once. A failed batch is logged and discarded; other batches can continue. HTTP 200 is not enough: the sender checks `JobResponse.success` and the upload SHA256. Temporary uploads are cleaned up after success or failure. No failure list or automatic retry queue is retained. Restart the source after fixing connectivity or size limits to reconcile and queue missing or stale snapshots again. New local changes can also queue a Task again.

If startup reconciliation fails, the source logs the error and continues without a full replay. Subsequent local changes can still be sent; restarting after the target recovers repairs existing gaps.

The receiver rejects replacements or deletions of active Tasks and rolls back the current apply operation on failure. Same-ID terminal directories are replaced in full. This is not historical versioned backup.

## Verification

1. Submit a Task with a configured name and wait for terminal status and the next flush.
2. Compare target metadata and artifact SHA256 values.
3. Restart the source: identical snapshots should not be queued.
4. Rerun a named Task or update an artifact: startup comparison should queue the changed snapshot.
5. For transfer errors, inspect logs, fix the cause, and restart to repair gaps.

For manual transfers, upload a complete Task archive using `POST /files`, then call `sync_tasks` with `answer.path`. The manual API still supports explicit deletions; the automatic sender never sends them.

[Scheduling](scheduling.md) · [Remote machines](remote-machines.md) · [Synchronization API](../api/plugins-sync.md)
