# Result display synchronization

Task synchronization publishes terminal **display replicas**, not executable workspace backups. `task_names` matches the final segment of `<task type>#<registration>#<task name>`; an empty list includes every name. Composite and child Tasks are selected independently by the same rule.

## Content and semantics

A replica contains `metadata.json`, execution events, published outputs and the files required by their model or online manifests. Upstream `inputs/`, pinned `model_snapshot/`, unreferenced files, temporary workspaces, external logs and plugin environments are excluded. Local hard-link input snapshots remain intact.

Source metrics and research protocols retain the original run semantics. `metadata.replica` has `purpose: display`, source and policy digests, actual file sizes and SHA256 values, omitted paths/reasons, sampled row counts/date coverage and the source log path. The local `log_path` is empty. Studio labels replicas; file coverage and omissions expand on demand. Consumers reject replicas as research inputs; replicas are never forwarded as synchronization sources.

## One budget

The application-level `transfer_budget_bytes` defaults to 536870912 (512 MiB). It controls each archive's uncompressed total, including metadata and tar overhead, and the upload limit. The sender negotiates the smaller source/receiver budget using `task_sync_index`. There is no independent file-size option. `max_file_bytes` and `max_archive_bytes` are rejected.

Complete files are kept whenever they fit. Otherwise, date-keyed business Parquet files are rewritten using a shared suffix of recent complete `trade_date` values. Sampling checks actual encoded sizes and preserves types and file metadata; it never truncates bytes or individual days. Models, JSON, metadata, report aggregates, transaction ledgers and reference calendars are not sampled. If the newest complete day cannot fit, sampleable data is omitted with a reason. Required non-sampleable content exceeding the budget is rejected. Original files and metrics never change.

## Configuration

Use the same application budget on both services. Receivers do not need a sync component. Set the configured target's token to the receiving service's authentication token.

```yaml
extends: default
transfer_budget_bytes: 536870912
targets:
  - address: http://archive.example:1024
    token: ${AXONX_SYNC_REMOTE_TOKEN}
components:
  sync:
    default:
      backend: local
      target: http://archive.example:1024
      task_names: [research-model]
      max_archives_per_flush: 4
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

## Reconciliation, retries and cleanup

`task_sync_index` returns `transfer_budget_bytes` and a `tasks` map containing `source_digest` and `policy_digest` for each verified replica. Startup compares published source content and the current sampling policy. Identical replicas are skipped; reruns, output changes or budget changes produce replacements. Excluded input changes alone do not require retransmission.

Repository events queue terminal source Tasks. Missed watcher events trigger reconciliation. Startup index failures retry on subsequent flushes. Temporary planning/upload/commit failures remain queued; deterministic invalid outputs or non-sampleable budget failures are reported instead of retrying every minute. Unattempted batches remain queued. Queue state is in memory; startup reconciliation repairs interrupted transfers. Local deletion never propagates automatically.

A Task replica fits entirely in one archive. The receiver verifies the exact file inventory, sizes and checksums, rejects active Task replacements, and atomically commits with rollback. Source sampling files and remote uploads are cleaned up on success, failure and cancellation. Cancellation waits for background staging work before deleting its files.

## Breaking format

Both services must use this display-replica format. Old complete-directory archives and old index responses are rejected; no legacy-reader or migration path is provided. Regenerate backtest artifacts using the unified `signals.parquet` schema before publishing them. Manual `sync_tasks` accepts prepared replica archives or explicit deletions, not arbitrary unmarked Task directories.

## Verification

Verify that matching parent/child Tasks appear; inputs are absent; samples retain complete recent days; original source files remain unchanged; actual hashes match the replica manifest; restart skips identical replicas; changed budgets/runs update replicas; transient failures recover; temporary files are removed.

[Scheduling](scheduling.md) · [Remote machines](remote-machines.md) · [Sync API](../api/plugins-sync.md)
