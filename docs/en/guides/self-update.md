# Service Update and Restart

A daemon-backed service exposes authenticated update Jobs. Keep the startup interpreter, working directory and configuration consistent.

## Choose an update method

```bash
axonx update_from_git
axonx update_from_pip
axonx restart_service
```

Choose one operation. Git mode requires the running source to belong to the startup repository and needs git/npm; it fast-forwards the current branch, builds Studio and reinstalls source packages. Pip mode upgrades axonx and axonx-studio, rejecting source/editable shadowing. Restart skips package changes and reloads the application with the original startup arguments/environment. These Jobs accept no force argument.

## Remote update

After editing, committing and pushing the code locally, run from your local machine, replacing the example address with your target service:

```bash
# Set AXONX_TARGET_TOKEN to the target service's token beforehand
axonx update_from_git --target axonx.example.com:1024

# Check the result after the service is reachable again
axonx get_update_status --target axonx.example.com:1024
```

The remote machine stops the application service → runs `git pull --ff-only` → builds Studio → reinstalls AxonX and Studio → verifies dependencies and imports → starts the new service.

## Admission and response boundary

The updater reserves maintenance, prepares a durable record and defers commit until the invoking HTTP/MCP response has finished. New local Jobs are rejected during maintenance except version and get_update_status. Preparation failure releases admission. Acceptance is not completion.

The daemon stops/replaces its application service. Manual service-owned CLI processes stop with that service; daemon-owned scheduled commands continue. Coordinate source/dependency changes with ongoing scheduled work yourself; running processes are not version-isolated. The daemon stays as supervisor while the service process is replaced.

## Durable results and failures

Save the returned update_id and query after the service is reachable again:

```bash
axonx get_update_status --update-id ACTUAL_UPDATE_ID
axonx get_update_status
```

Records and update.log live below the service's workspace daemon identity directory: `daemon/<identity>/updates/<update_id>/`. Phases include accepted, fetching, building, installing, verifying, starting, succeeded and failed. Success requires the replacement service to report ready. Status returns the record and up to 64 KiB of log.

The service can be unavailable during build/install/restart. Update failures are recorded and the daemon attempts service startup again; partial Git/pip changes are not rolled back. Inspect local daemon/service logs when imports prevent API recovery. A later daemon startup marks unfinished update records failed. Embedded applications need an explicit host update backend and response-completion boundary.

Sources: [updater](../../../axonx/app/components/updater/local.py), [daemon control](../../../axonx/daemon/client.py), [supervisor](../../../axonx/daemon/supervisor.py).
