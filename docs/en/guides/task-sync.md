# Result Display Synchronization

Synchronization creates bounded display replicas. Each rule selects a registered workflow and a publication time: `terminal` waits for the parent and its selected descendants to succeed or fail; `live` captures their current state on each flush. `model_names` selects model branches with shell-style patterns; an empty list includes every model. An empty `rules` mapping selects no workflows.

![Source evidence and read-only display replicas in separate workspaces](../../figures/concepts/workspace.svg)

Follow the dashed copy path to the display workspace. Research consumers continue to read verified source artifacts; the replica path is for inspection.

## Content and semantics

Replicas include metadata, progress evidence and referenced published artifacts. They exclude environments, raw workspaces and unreferenced files. Missing files are recorded in replica.omitted; source declarations and metrics remain unchanged. Replicas cannot execute or be reused as mutable research inputs, and are not forwarded as synchronization sources.

## One budget

transfer_budget_bytes (default 512 MiB) bounds upload/archive size including tar overhead. Sender and receiver use the smaller budget. Large date-keyed Parquet outputs may be sampled to a shared suffix of complete trade dates; record sizes, revisions, source rows and coverage distinguish replicas from complete source artifacts. Other files can be omitted rather than silently truncated.

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
      task_index: default
      model_names: ["experiment-*"]
      rules:
        research: terminal
        online: live
        compare: terminal
      max_archives_per_flush: 4
      timeout_seconds: 300
jobs:
  sync_flush:
    parameters: { type: object, properties: {}, additionalProperties: false }
    steps:
      - backend: sync_flush_step
        sync: default
```

Invoke `axonx sync_flush` explicitly after configuring this optional Job. The default leaves it disabled. Cron supports local Task exec commands, so do not copy a Job schedule block into cron. A host workflow can invoke flush periodically. The sync component depends on task_index.

## Reconciliation, retries and cleanup

Index events queue eligible source records; flush reconciles missed events, prepares bounded batches, uploads archives and applies them via sync_tasks. Temporary failures remain eligible for later flushes; unsafe or oversized evidence reports errors/omissions. Inspect the returned synchronization report. Upload cleanup and target reconciliation belong to synchronization consumers.

## Selected workflow snapshots

`TaskSnapshot` records `source_id`, `root_task_id`, `root_started_at`, `captured_at`, ordered `revision`, `when` and `model_names`. Both publication modes use the same task-tree selection, budget, delta transfer and atomic replacement. Child membership follows recorded Task IDs and start times. When a fixed-name child has a newer execution, its old invocation remains in source metadata and execution history, while display snapshots omit that replaced branch. New child payloads are never attached to old invocation records. Missing children and changes during capture remain errors. Excluded branches are not read, so their replacement cannot block another model's snapshot.

Selection reuses input `models`, each model's `task_name` and existing child `node_name`. Model lists use `MODEL-REGISTRATION` nodes; signal-time mappings use `MODEL-SLOT-REGISTRATION`. Normal `run_task(task_name=...)` calls derive this name automatically. Calls with hashed Task directory names supply the explicit logical `node_name`. Shared calls keep the default node name equal to their registration. Selected branches retain all exact descendant Runs. Parent progress matches the model node (`MODEL` or `MODEL-SLOT`) in step `group` or colon-separated `name` parts. A partially selected parent with an unrecognized child node is rejected.

For a partial view, the sender projects named model entries in parent inputs/results, keeps selected and shared children/steps, and omits aggregated parent artifacts and mixed parent logs. Selected child publications and bounded logs remain available. The source metadata is unchanged. Replacing a view removes obsolete display replicas owned by that same source/root group; unrelated Tasks are retained.

## Verification

Check source/target, Task start identity, available artifact coverage and target read-only labels. Synchronization does not resume processes, install plugins, transfer credentials or replace backup.

Sources: [sync component](../../../axonx/app/components/sync/local.py), [replica builder](../../../axonx/app/components/sync/replica.py).
