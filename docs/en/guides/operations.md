# Log troubleshooting, backup, and recovery

When troubleshooting, first confirm the execution machine, Task ID, and run_id, then distinguish protocol connections, worker execution, and research display. Backup and recovery must account for files, plugin environments, and external credentials together; restoring historical records does not restore interrupted processes.

## Establish basic status

```bash
axonx version
axonx machine_status
axonx list_plugins
axonx list_task_statuses
```

Record service and plugin versions. Commands for remote tasks should include the original target address; reading the same Task ID locally does not prove you are viewing the same machine.

Query `/health` with a token to check protocol connectivity. A 401 caused by a missing token does not indicate worker failure; see [Authentication guide](authentication.md).

## Log sources

| Source                      | Helps determine                                                               |
| --------------------------- | ----------------------------------------------------------------------------- |
| Service console and log_dir | Startup, configuration, forwarding, watcher, scheduling, and component errors |
| status.error / exit_code    | Final error for a Task run                                                    |
| read_task_log               | Detailed worker logs from steps, plugins, and model libraries                 |
| events.jsonl                | Progress event replay, distinct from text logs                                |
| metadata.json               | Current input, output, state, errors, and child invocations                   |

```bash
axonx status --task-id '<Task ID>'
axonx read_task_log --task-id '<Task ID>' --offset -1 --limit 65536
```

Log windows use byte offsets. Read the tail first to find the exception, then expand or specify a window as needed. If status.log_path points to an external log directory, migrating the workspace may also require restoring logs.

## Submission succeeds but the Task fails

1. Check run_id in the handle to rule out a fixed-name rerun.
2. Inspect the final state, error, and exit_code.
3. Inspect the last failed step and Task logs.
4. Check plugin inputs, upstream files, external data permissions, and model dependencies.
5. Rerun with a new task_name, retaining the failure record for comparison.

`submit.success=true` only means acceptance succeeded. The success from `wait_task` corresponds to the final succeeded state; HTTP 200 alone should not establish research success.

## Worker failures and status reconciliation

Each new Task record includes a stable `machine_id` derived from the OS machine identity and a `process_started_at` timestamp. The ID survives service and machine restarts; it does not depend on the service port, workspace, IP address, or hostname. Queued records identify the submitting service process until the worker publishes its own identity. In-process children record the same machine and process instance as their parent.

If running persists for a long time, first check whether the process is still running, whether the current service manages this run, whether logs continue growing, and whether the disk is writable. Do not determine process liveness across machines solely from a pid in a file.

While the owning service is running, its supervisor detects a forcibly killed worker. At startup and before named submission, recovery rereads the exact Run and only settles an identified local process instance that has exited. Matching child records retain Run ID and worker-identity checks; successful results remain unchanged. Records without machine identity, foreign records, replicas, and unverifiable process instances are left unchanged. Recovery does not adopt or signal surviving workers, resume Python execution, reexecute Tasks, or replay cron triggers.

Legacy records without `machine_id` remain unchanged regardless of their creation time; there is no lock-based recovery or handoff grace period. Use a distinct Task name when the previous record cannot be attributed to this machine.

Recovery replaces stale lifecycle state; it does not resume Python execution, automatically reexecute Tasks, or replay missed cron triggers. After reviewing interrupted outputs, submit a new Run if needed. The former reaper_interval_seconds setting remains removed, and there is no periodic process scan. New fields are optional when reading legacy records; older readers that reject unknown fields must be upgraded before sharing newly written records.

## Files exist but the page has not updated

Repository watches and polls record changes by default, and parameters such as debounce make short delays normal. Check JSON validity, consistency of task_id/type with the directory, and whether the service uses the expected workspace.

When watcher observation windows are missed, Repository/synchronization rechecks records. Indexes can be rebuilt from valid metadata, but this does not repair corrupt JSON or missing artifacts.

Research pages use directories containing metadata. Failed tasks, base demos, and tasks missing metadata may not appear in research result pages; valid metadata does not guarantee all chart fields are present.

## Backup checklist

| Content                                                  | Why it is needed                                                                      |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Complete workspace                                       | Task records, research artifacts, raw data, and Agent state                           |
| log_dir                                                  | Execution logs stored separately from task directories                                |
| Service configuration and environment-variable inventory | targets, paths, schedules, and connection parameters                                  |
| Plugin source/wheels and versions                        | Restore the same algorithms for reruns                                                |
| Python and model dependency information                  | Restore data formats, device libraries, and model-loading conditions                  |
| External credentials                                     | Preserve through a separate secure method; documentation examples cannot recover them |

On Linux/macOS, use your own backup tools after stopping writes. For example, if the workspace and logs are in the current directory:

```bash
# Run after confirming the service and exec processes have stopped writing
mkdir -p ./backup
cp -a ./.axonx ./backup/workspace
cp -a ./logs ./backup/logs
```

Choose a new backup destination before repeating to avoid nested paths or overwriting unknown backups. For large datasets, use snapshot or incremental backup tools; the commands only illustrate file copying.

## Recovery order

1. Stop accepting new tasks and file writes.
2. Restore the workspace, logs, and configuration at the target location, checking permissions and absolute paths.
3. Install matching AxonX, plugins, and model dependencies.
4. Start the service so Repository rescans valid records.
5. Compare task counts, metadata, and artifact size/sha256 against the backup.
6. Run demo under a distinct name, then verify research plugins on a small scale.

The pid and log_path in old status records describe the original environment and do not imply a corresponding active process on the target machine. Restoring files does not automatically restore the in-memory state of ongoing training.

## Synchronization versus backup

Task synchronization operates on terminal directories and may replace same-name target directories and propagate deletion. It does not retain a complete history at arbitrary points in time, and excludes workspace raw data, Agent sessions, external logs, and plugin environments.

For recovery that can undo changes, maintain separate versioned backups. See [Task synchronization](task-sync.md) for synchronization budgets, rollback, and retries.

[Deployment](deployment.md) · [Workspace](../concepts/workspace.md) · [Task lifecycle](../concepts/task-lifecycle.md)
