# Task lifecycle

`axonx exec` discovers and executes an installed Task in its current process. App reads workspace data and serves queries, subscriptions and views; Task definitions are queried in a separate CLI process, without importing research plugins into App.

```text
exec → validation and directory transaction → running → succeeded / failed
```

The first metadata record is `running`, with `task_id`, `run_id`, `machine_id`, a positive `pid`, timezone-aware `process_started_at`, and creation/start times. `queued` is removed. Process creation time identifies reused PIDs; Task start time cannot replace it.

## Observation and reconciliation

App checks original local `running` records at startup and on every poll, including records whose file attributes are unchanged. A matching live process leaves metadata unchanged. Confirmed exit or PID reuse settles the Run, unfinished steps and child invocation records as `failed`, with framework exit code `1` and the detection time in the error. `finished_at` records detection time, not a guessed exit time or signal.

Foreign records, display replicas and process permission failures are not rewritten. A live process does not establish that computation is healthy. Service restart does not stop independent exec processes, retry Tasks or replay cron slots.

## Reruns and termination

A fixed Task ID can replace a terminal Run: log `Overwrite`, clear old Run files and retain `persistent/`. A stale local `running` record is checked and reconciled first. Live or unverifiable runs block replacement and report an exact kill command. Foreign runs require action on their execution machine; `machine_id` does not reveal a service address. Malformed records, symlinks and display replicas are never blindly replaced.

```bash
axonx kill --task-id '<Task ID>' --run-id '<Run ID>'
axonx kill --task-id '<Task ID>' --run-id '<Run ID>' --target '<host:port>'
# Explicit force termination
axonx kill --task-id '<Task ID>' --run-id '<Run ID>' --force true
```

Kill checks the original local Run, PID and process creation time. It sends SIGTERM and waits for `--timeout` seconds (default 5); timeout does not escalate automatically. `--force true` explicitly sends SIGKILL. Composite children share their execution process, so termination affects that process and its descendants; the root Run is used when identifiable. Unfinished records for that process are reconciled after exit.

New Run creation and observation use short transactions under workspace `.task-records/`. Checking, cleanup and initial publication form one transaction; no lock is held during execution. This framework directory is hidden and protected in the workspace browser. Do not manually mutate active records or clear a workspace concurrently.

Old internal paths, metadata without process identity and queued states have no compatibility reader or automatic migration. Preserve needed artifacts and rerun. `wait_task` always checks the exact Task/Run pair.
