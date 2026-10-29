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

## Service updates and restart

A daemon-backed service exposes authenticated update Jobs. Keep the startup interpreter, working directory and configuration consistent.

### Choose an update method

```bash
axonx update_from_git
axonx update_from_pip
axonx restart_service
```

Choose one operation. Git mode requires the running source to belong to the startup repository and needs git/npm; it fast-forwards the current branch, builds Studio and reinstalls source packages. Pip mode upgrades axonx and axonx-studio, rejecting source/editable shadowing. Restart skips package changes and reloads the application with the original startup arguments/environment. These Jobs accept no force argument.

### Remote update

After editing, committing and pushing the code locally, run from your local machine, replacing the example address with your target service:

```bash
# Set AXONX_TARGET_TOKEN to the target service's token beforehand
axonx update_from_git --target axonx.example.com:1024

# Check the result after the service is reachable again
axonx get_update_status --target axonx.example.com:1024
```

The remote machine stops the application service → runs `git pull --ff-only` → builds Studio → reinstalls AxonX and Studio → verifies dependencies and imports → starts the new service.

### Admission and response boundary

The updater reserves maintenance, prepares a durable record and defers commit until the invoking HTTP/MCP response has finished. New local Jobs are rejected during maintenance except version and get_update_status. Preparation failure releases admission. Acceptance is not completion.

The daemon stops/replaces its application service. Manual service-owned CLI processes stop with that service; daemon-owned scheduled commands continue. Coordinate source/dependency changes with ongoing scheduled work yourself; running processes are not version-isolated. The daemon stays as supervisor while the service process is replaced.

### Durable results and failures

Save the returned update_id and query after the service is reachable again:

```bash
axonx get_update_status --update-id ACTUAL_UPDATE_ID
axonx get_update_status
```

Records and update.log live below the service's workspace daemon identity directory: `daemon/<identity>/updates/<update_id>/`. Phases include accepted, fetching, building, installing, verifying, starting, succeeded and failed. Success requires the replacement service to report ready. Status returns the record and up to 64 KiB of log.

The service can be unavailable during build/install/restart. Update failures are recorded and the daemon attempts service startup again; partial Git/pip changes are not rolled back. Inspect local daemon/service logs when imports prevent API recovery. A later daemon startup marks unfinished update records failed. Embedded applications need an explicit host update backend and response-completion boundary.

Sources: [updater](../../../axonx/app/components/updater/local.py), [daemon control](../../../axonx/daemon/client.py), [supervisor](../../../axonx/daemon/supervisor.py).
