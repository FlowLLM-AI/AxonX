# Service update and restart

`axonx start --config default --cron research` runs a stable daemon with separate HTTP and cron workers. Cron requests local exec processes from the daemon. These Tasks remain running when HTTP and cron are replaced. The daemon never reads or rewrites Task metadata.

In Studio, open **System management → Environment → Update or restart service** on the selected machine. Updates require authentication and the configured update/status Jobs. Embedded ASGI applications do not provide a process daemon.

## Update in place

```bash
axonx update_from_git
axonx update_from_pip
axonx restart_service
```

Connection options select the service machine. Git updates run `git pull --ff-only` in the startup repository on its current branch and upstream. They do not reset the branch or clean untracked files. Divergence or conflicting local changes fail the update. Git and Node.js/npm must be installed. The updater builds Studio with `npm ci` and `npm run build`, then installs backend and Studio from that repository in editable mode.

Pip updates run the service interpreter's `-m pip install --upgrade axonx axonx-studio`. Source installations and imports shadowing installed packages must use Git updates. Plugins are not upgraded automatically. Restart-only skips Git, npm and pip.

Source, packages and dependencies are updated in their existing locations. There are no release copies or version-isolated environments. Running Tasks are not signalled, but their later imports, subprocesses and file reads can see changed code or dependencies.

## Process ownership

The invoking HTTP, SSE or MCP response completes before the daemon commits the operation. The daemon stops cron first, preventing new triggers, while existing exec children continue. The updater runs as a temporary child; HTTP stays available for update status during builds and installation. Afterwards the daemon stops and replaces HTTP, then starts a fresh cron worker using the original startup arguments and directory.

Success requires the new HTTP listener and configured cron worker to report ready. The daemon PID stays unchanged; HTTP and cron PIDs change. Crashed workers restart with backoff. Task processes are reaped and their exit codes logged, without automatic retry or restart.

Studio polls status every three seconds while visible and reconnects during HTTP replacement. External build/install commands have a 30-minute timeout and clean up their own process groups on completion, timeout or interruption.

## Status and failures

```bash
axonx get_update_status
axonx get_update_status --update-id YOUR_UPDATE_ID
```

A successful update response means acceptance. Save `answer.update_id` and wait for the terminal record. Records and the updater snapshot live under `<workspace>/daemon/<instance>/updates/<update_id>/`; the instance identifies hostname, bind address, port and startup directory. `get_update_status` returns the record and at most 64 KiB of log tail. Unscoped legacy records are not read.

Phases are `accepted`, `fetching`, `building`, `installing`, `verifying`, `starting`, `succeeded` and `failed`. Build/install failures and unexpected updater exits stay failed while the daemon attempts worker startup. Partial source/package changes remain; no rollback is attempted. A daemon restart marks its interrupted updates failed rather than resuming them.

## Daemon lifetime

`axonx start` remains a foreground command suitable for external supervision. Its standard-library daemon script is copied into the private runtime directory at startup and does not import application code. Ordinary service updates leave that process unchanged. A per-instance lock prevents duplicate daemons. Worker stdout/stderr is retained in `service.log` and `cron.log` under the same directory; normal application and Task logs retain their configured locations.

Ctrl+C or SIGTERM stops HTTP, cron and an active updater, then exits the daemon. Existing cron exec processes continue; a later daemon does not adopt or rerun them. Task completion still belongs to their Runner. OS service-manager policies or a host shutdown can terminate these processes; application-level restart does not stop the outer service unit.
