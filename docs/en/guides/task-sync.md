# Result display synchronization

Task synchronization publishes **display replicas**, not executable workspace backups. Ordinary Tasks sync only after completion; explicitly configured live parents sync on every component flush. `task_names` matches the final segment of `<task type>#<registration>#<task name>`; an empty list includes every name. For ordinary Tasks, composites and children are selected independently. `live_task_ids` selects exact parents and automatically follows their exact child Runs regardless of `task_names`.

## Content and semantics

A replica contains `metadata.json`, execution events, published outputs and the files declared by their model or online manifests. Only publication artifact maps, comparison results, online commits and previous history nodes declare dependencies; provenance fields and composite summaries do not declare local files. Upstream `inputs/`, pinned `model_snapshot/`, unreferenced files, temporary workspaces and plugin environments are excluded. Local hard-link input snapshots remain intact.

Missing published files are recorded in `replica.omitted`; they do not block status, logs or available outputs. Source metadata and artifact declarations remain unchanged. Restored files change the source revision and are included on the next synchronization. Display synchronization does not validate research signal formats.

Source metrics and research protocols retain the original run semantics. `metadata.replica` has `purpose: display`, source and policy revisions, actual file sizes and file revisions, omitted paths/reasons, sampled row counts/date coverage and the source log path. The local `log_path` is empty. Studio labels replicas; file coverage and omissions expand on demand. Consumers reject replicas as research inputs; replicas are never forwarded as synchronization sources.

## One budget

The application-level `transfer_budget_bytes` defaults to 536870912 (512 MiB). It controls each archive's uncompressed total, including metadata and tar overhead, and the upload limit. The sender negotiates the smaller source/receiver budget using `task_sync_index`. There is no independent file-size option. `max_file_bytes` and `max_archive_bytes` are rejected.

Complete files are kept whenever they fit. Otherwise, date-keyed business Parquet files are rewritten using a shared suffix of recent complete `trade_date` values. Sampling checks actual encoded sizes and preserves types and file metadata; it never truncates bytes or individual days. Models, JSON, metadata, report aggregates, transaction ledgers and reference calendars are not sampled. If the newest complete day cannot fit, sampleable data is omitted with a reason. If content still exceeds the budget, the largest remaining files are omitted first, with logs retained preferentially. Metadata alone exceeding the budget is rejected. Original files and metrics never change.

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
    requires_auth: true
    steps:
      - backend: sync_flush_step
        sync: default
```

## Reconciliation, retries and cleanup

`task_sync_index` returns `transfer_budget_bytes` and a `tasks` map containing `source_revision` and `policy_revision` for each verified replica. The first flush compares Run IDs, published file sizes/modification times and the current sampling policy; service startup never waits for synchronization. Identical replicas are skipped; reruns, output changes or budget changes produce replacements. Excluded input changes alone do not require retransmission.

Repository events queue terminal source Tasks. Missed watcher events trigger reconciliation. Index failures retry on subsequent flushes. Temporary planning/upload/commit failures remain queued; unsafe paths and metadata exceeding the budget are reported. Missing outputs sync with explicit omissions instead of retrying the entire Task. Unattempted batches remain queued. Queue state is in memory; first-flush reconciliation repairs interrupted transfers. Local deletion never propagates automatically.

A Task replica fits entirely in one archive. The receiver verifies the exact file inventory, sizes, rejects native active Task replacements, and atomically commits with rollback. Source sampling files and remote uploads are cleaned up on success, failure and cancellation. Cancellation waits for background staging work before deleting its files.

## Continuous parent snapshots

`live_task_ids` defaults to `[]`. Each flush captures parent metadata, step progress, current child Runs and published display artifacts as one group in one archive. Each `sync_flush` call controls synchronization; invoke it manually or from an external scheduler. Ordinary Tasks retain terminal-only behavior. Run identity changes or missing children defer the whole group until the next flush; unpublished working files are never copied.

Live replicas omit input features, model weights, source/debug snapshots and mutable event journals. Activities and steps are already present in captured metadata. Both ordinary and live replicas include at most the latest 1 MiB of their own log, confined to the configured source log directory and reduced for small budgets. `replica.log` records retained start/end byte offsets; `read_task_log` uses original source offsets and resets when the requested bytes have expired. A changed log tail is resent as a bounded file; unchanged logs and output files are reused by file revision. This is file-level delta synchronization, not a byte-level append protocol. Full logs remain on the source under the normal retention policy.

`replica.snapshot` identifies the source workspace, parent Task/Run, capture time and ordered revision. `task_sync_index` accepts `live_task_ids` and returns one `tasks` index with source/policy revisions, Run IDs and complete replica file records. Delta archives retain the complete file manifest; the receiver hydrates missing unchanged files only from a matching verified local Run, then validates and commits the whole group with rollback. Old revisions, conflicting sources, terminal-to-active regression and native active Tasks are rejected. Completed group members may sync independently when the Run ID is unchanged; a newer snapshot from the same source may reference a shared child under another parent. No process is transferred. Replicas cannot be cancelled or used as research inputs. Active groups refresh capture time even without progress changes, so Studio can distinguish an idle source from delayed synchronization. Live groups divide the negotiated total budget among members before preparation, sampling or omitting files within each share. Metadata that cannot fit its share is reported and retried on subsequent flushes.

Studio polls lists, details and followed logs every 5 seconds while visible, including completed replicas so their final snapshots arrive. Network freshness still follows the flush frequency. Both sender and receiver must be upgraded before enabling `live_task_ids`; unsupported receivers are reported and retried, without falling back to terminal copies of the live group.

## Breaking format

Upgrade both sender and receiver together. Persisted SHA-256 replica manifests remain readable and are replaced on the next synchronization; new uploads and indexes use file revisions. Old complete-directory archives and old index responses are rejected. Manual `sync_tasks` accepts prepared replica archives or explicit deletions, not arbitrary unmarked Task directories.

## Verification

Verify that matching parent/child Tasks appear; inputs are absent; samples retain complete recent days; original source files remain unchanged; actual file sizes match the replica manifest; restart skips identical replicas; changed budgets/runs update replicas; transient failures recover; temporary files are removed.

[Scheduling](scheduling.md) · [Remote machines](remote-machines.md) · [Sync API](../api/plugins-sync.md)

All replicas share one preparation path, index, pending queue, archive budget and sender. Each group has its own staging directory. Groups stay indivisible during packing; groups sharing a Task use separate archives so their snapshots cannot overwrite one another during preparation or validation. Delta batches reserve their fully hydrated size. A rotating order prevents continuously active groups from starving later groups or completed tasks. Unchanged completed groups are skipped.

Synchronization and uploads do not checksum payload bytes. A bounded metadata fingerprint identifies Run identity, file sizes and modification times; same-size changes that preserve modification time are not detected. Research artifacts use size/mtime revisions; plugin installation retains wheel checksums. Completed unchanged groups are skipped before preparation; idle active groups refresh only metadata and reuse remote files. Preparation stops once the archive quota is exhausted, with at most one lookahead group. Gzip uses level 1. Live flushes refresh the remote index without rescanning ordinary sources unless reconciliation or a budget change requires it.
