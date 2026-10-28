# Operations and Recovery

## Establish basic status

```bash
axonx version
axonx diagnose
axonx plugin list
axonx list_task_statuses --detail summary
```

Keep the execution machine, workspace, Task ID and started_at together. Local plugin list describes the CLI interpreter; add --target to inspect a service environment.

## Log sources

Use service/daemon logs for connectivity, process launch and update problems. Task metadata.log_path identifies execution logs; read_task_log provides bounded byte chunks. Scheduled stdout/stderr is also captured in the configured log directory under cron/entry-N.log. File existence is not proof of successful business evaluation.

## Execution fails or disconnects

Check native command exit_code, Task state/error, process identity and business outputs separately. Before retrying after a disconnect, inspect whether the Task started and whether started_at changed. Manual remote CLI requests own processes; cancellation or service shutdown can terminate their groups.

## Stale records

Observations do not rewrite running records. Runtime startup and explicit kill can reconcile confirmed dead local processes, matching machine/PID/process start time. Inaccessible and foreign processes stay unverified; use the source service and workspace. A shared workspace does not transfer ownership to an observing service.

## Backup and recovery

Back up Task directories and persistent/ together with source/plugin versions, configuration, credentials, separate logs and Agent state when needed. Pause writers before copying related files. Restoring records does not restore processes. Reinstall the matching plugins, restore configuration/environment, start the intended service and verify data/model revisions before new execution.

Display synchronization is bounded evidence replication, not a full backup; omitted/sampled files and environments need separate preservation. Indexes can be rebuilt from valid metadata. Do not delete live directories to repair execution.

[Task management](task-management.md) · [Synchronization](task-sync.md) · [Self-update](self-update.md)
