# One-way task display synchronization

The source pushes new or changed selected task groups into a dedicated remote display workspace. It does not compare remote state, pull changes, propagate source deletions or remove directories dropped by a selection rule. Matching destination directories are replaced completely; unlisted remote directories remain untouched.

## Configuration

```yaml
extends: default
targets:
  - address: http://display:1024
    token: ${DISPLAY_TOKEN}
components:
  sync:
    default:
      backend: local
      target: http://display:1024
      model_names: ["experiment-*"]
      rules:
        research: terminal
        online: live
        compare: terminal
      max_archives_per_flush: 4
      timeout_seconds: 300
jobs:
  publish_display:
    backend: scheduled
    expression: "* * * * *"
    enable_serve: false
    steps:
      - backend: sync_flush_step
        sync: default
```

The internal Job runs once per minute in the App timezone. It reuses the pipeline Steps, argument validation and cancellation lifecycle. Scheduled invocations are sequential and missed times are not replayed. Set `enable_serve: true` to also allow manual HTTP/MCP invocation. Stopping the service cancels its scheduled Jobs; research Task processes retain their existing daemon ownership.

## Source selection and change detection

`rules` maps workflow registrations to `terminal` or `live`. Terminal publication waits for the parent and selected descendants to finish; live publication captures current evidence. `model_names` uses shell-style patterns, with an empty list including all models. Empty rules select nothing.

Each invocation scans source metadata. Version detection uses execution identity, file inventory, sizes, nanosecond mtimes and publication policy without reading payloads for content hashing. Successful versions are retained in sender memory. Unchanged groups are skipped, failures are retried on the next invocation, and source service restart republishes selected groups once. Remote deletion or modification does not trigger retransmission. Changing file contents while preserving size and mtime is not detected.

Model selection reuses model `task_name`, logical child `node_name` and progress `name`/`group`. Selected views retain available matching child executions and shared descendants. Parent parameters, results and progress are projected to the selected models; mixed parent logs and aggregate artifacts are omitted. Replaced child executions are excluded rather than associated with old parent calls. Sources remain unchanged.

## Transfer and display

The sender creates complete bounded display directories and submits them through `POST /upload?mode=replace`. Each archive contains one workflow group and its selected descendants; `max_archives_per_flush` bounds each invocation, with subsequent invocations continuing through other roots. The receiver only validates and replaces files. Its existing `task_index` discovers supported metadata at the next scan, every five seconds by default. No receiver-side synchronization component, receipt, dedicated Job or task metadata parser is required for file transfer.

`transfer_budget_bytes` defaults to 512 MiB and bounds both upload bytes and expanded archive size. Configure the source budget no larger than the receiver's. Oversized date-keyed Parquet artifacts can be sampled to a shared suffix of complete trading days; other files can be omitted explicitly. Failures and omissions are reported. Display metadata retains source identity, source/policy revisions, file coverage and the selected workflow snapshot. Display replicas cannot execute, become research inputs or be forwarded as source tasks.

Source staging under `tmp/sync/` is removed after each group. Receiver staging under `tmp/files/` is removed after success or a completed rollback; failed rollbacks retain original directories for recovery. The operation is file replacement, not a backup or process/environment migration. Use separate display workspaces because supplied paths overwrite matching directories.
