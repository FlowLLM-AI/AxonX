# Result display synchronization

Task synchronization publishes **display replicas**, not executable workspace backups. Ordinary Tasks sync only after completion; explicitly configured live parents sync on every component flush. `task_names` matches the final segment of `<task type>#<registration>#<task name>`; an empty list includes every name. For ordinary Tasks, composites and children are selected independently. `live_task_ids` selects exact parents and automatically follows their exact child Runs regardless of `task_names`.

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
      live_task_ids: [composite#online#research-model]
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

A Task replica fits entirely in one archive. The receiver verifies the exact file inventory, sizes and checksums, rejects native active Task replacements, and atomically commits with rollback. Source sampling files and remote uploads are cleaned up on success, failure and cancellation. Cancellation waits for background staging work before deleting its files.

## Continuous parent snapshots

`live_task_ids` defaults to `[]`. Each flush captures parent metadata, step progress, current child Runs and published display artifacts as one group in one archive. No new timer or watcher is introduced: the existing flush schedule controls synchronization. Ordinary Tasks retain terminal-only behavior. Run identity changes or missing children defer the whole group until the next flush; unpublished working files are never copied.

Live replicas omit input features, model weights, source/debug snapshots and mutable event journals. Activities and steps are already present in captured metadata. Each Run includes at most the latest 1 MiB of its own log, confined to the configured source log directory. `replica.log` records retained start/end byte offsets; `read_task_log` uses original source offsets and resets when the requested bytes have expired. A changed log tail is resent as a bounded file; unchanged logs and output files are reused by checksum. This is file-level delta synchronization, not a byte-level append protocol. Full logs remain on the source under the normal retention policy.

`replica.snapshot` identifies the source workspace, parent Task/Run, capture time and ordered revision. `task_sync_index` accepts `live_task_ids` and returns one `tasks` index with source/policy digests, verified Run IDs and file hashes. Delta archives retain the complete file manifest; the receiver hydrates missing unchanged files only from a matching verified local Run, then validates and commits the whole group with rollback. Old revisions, conflicting sources, terminal-to-active regression and native active Tasks are rejected. No process is transferred. Replicas cannot be cancelled or used as research inputs. Active groups refresh capture time even without progress changes, so Studio can distinguish an idle source from delayed synchronization. Live groups must fit the negotiated total budget; oversized groups are reported and retried on subsequent flushes.

Studio polls lists, details and followed logs every 5 seconds while visible, including completed replicas so their final snapshots arrive. Network freshness still follows the flush frequency. Both sender and receiver must be upgraded before enabling `live_task_ids`; unsupported receivers are reported and retried, without falling back to terminal copies of the live group.

## Breaking format

Both services must use this display-replica format. Old complete-directory archives and old index responses are rejected; no legacy-reader or migration path is provided. Regenerate backtest artifacts using the unified `signals.parquet` schema before publishing them. Manual `sync_tasks` accepts prepared replica archives or explicit deletions, not arbitrary unmarked Task directories.

## Verification

Verify that matching parent/child Tasks appear; inputs are absent; samples retain complete recent days; original source files remain unchanged; actual hashes match the replica manifest; restart skips identical replicas; changed budgets/runs update replicas; transient failures recover; temporary files are removed.

[Scheduling](scheduling.md) · [Remote machines](remote-machines.md) · [Sync API](../api/plugins-sync.md)

All replicas share one preparation path, index, pending queue, archive budget and sender. Groups stay indivisible during packing; delta batches reserve their fully hydrated size. A rotating order prevents continuously active groups from starving later groups or completed tasks. Unchanged completed groups are skipped.
