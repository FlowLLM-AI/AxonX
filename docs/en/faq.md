# Frequently Asked Questions

## Studio opens but data does not load

Static UI availability does not prove service/API availability. Check selected machine, token, /health and public Job catalog. A service without a token hides authenticated capabilities.

## Exec prints output but where is the Task record?

Exec waits for completion and prints business output. Find metadata under workspace/type/task_id/metadata.json, or query status with full detail. Retain task_id, started_at and target. A connection error alone does not establish whether a remote command started.

## How do I distinguish a same-name rerun?

Task ID names the current directory; started_at changes per execution. wait_task captures that value and rejects a replacement during its wait. Use distinct names to preserve independent experiments.

## Do upstream IDs execute a dependency chain?

No. upstream_task_ids declares input dependencies. Execute each stage explicitly, check success, then pass actual IDs. Parent/child invocations are a separate relationship.

## Why is an installed plugin missing in Studio?

Confirm the target interpreter and plugin list. Native remote commands do not upload local source. After installation, restart the persistent service to refresh its startup catalog and cached schemas; new exec processes already rediscover installed metadata. Follow the [multi-step deployment flow](plugins/management.md).

## Why does stopping an Agent not stop research?

An Agent turn and independent Task execution have separate ownership. cancel_agent_turn interrupts the model session. CLI kill stops a verified Task process; children share the root process. Cancelling an owned remote cli request can also stop that request's child process group.

## How do I remove a Task?

Stop writers, verify state/process ownership, then delete its workspace-relative directory through delete_entries. It deletes persistent data too and does not protect active Task processes. File deletion is not termination.

## Why is a running record stale?

Observation is read-only. Startup or explicit kill can reconcile confirmed dead local processes; foreign or inaccessible processes remain unverified. Use the source service, execution_target and workspace.

## What if a preview or replica is incomplete?

Inspect response truncation, sampling and omitted-file metadata. A display replica is observation evidence, not an executable backup. Missing market data can make a backtest provisional even when Task execution succeeded.

[Quickstart](getting-started/quickstart.md) · [Operations](guides/operations.md) · [Task contracts](reference/task-contracts.md)
