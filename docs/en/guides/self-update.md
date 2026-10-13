# Service self-update

A service started with `axonx start` can update its backend and Studio through authenticated Jobs. In Studio, open **Run → Environment → Update or restart service** on the selected machine. Set the service token before using this feature; update Jobs are hidden on unauthenticated services.

## Choose an update method

Studio defaults to **Source repository · origin/main**. Select the published-package method for a pip installation.

```bash
# Discard local source changes and move the startup repository to origin/main
axonx update_from_git

# Upgrade the stable published packages in the service's Python environment
axonx update_from_pip

# Explicitly cancel active managed Runs first
axonx update_from_git --force true
```

Client targeting and credentials follow the ordinary Job connection options. Updates execute on the selected service machine, not the client machine.

The Git method requires the service to load AxonX from the repository containing its original startup directory, with Git and the Studio-supported Node.js/npm installed. It fetches `origin/main` before discarding tracked source changes and untracked source files, then aligns the local `main` branch with the fetched commit. Ignored files remain, including the usual `.env`, `.venv`, and `.axonx/`. The configured workspace, log directory, Python environment, loaded `.env` file and untracked startup configuration files (including inherited files) also receive explicit cleaning exclusions. Runtime paths that overlap tracked source or the repository root are rejected. Both the current source and the fetched commit are checked before destructive changes. The original startup subdirectory must exist in the fetched commit. It builds Studio with `npm ci` and `npm run build`, then installs the backend and Studio from the repository in editable mode.

The pip method runs the service interpreter's `-m pip install --upgrade axonx axonx-studio`. No npm build is needed: the Studio Python package contains static assets. Source installations and imports that shadow the installed packages (including through `PYTHONPATH`) are rejected; use Git updates for source installations. Stable releases are selected by pip's normal upgrade behavior.

Use a dedicated writable Python environment for the service. Self-update does not coordinate other independent processes using that environment, upgrade research plugins, or guarantee that independently published package versions are compatible.

## Restart without updating

Select **Restart only** in Studio, or run:

```bash
axonx restart_service
# Explicitly cancel active managed Runs first
axonx restart_service --force true
```

Studio lists the operations configured on the selected service. A restart-only service needs `restart_service` and `get_update_status`; Git and pip update Jobs are optional.

This authenticated Job reuses the maintenance, shutdown and process replacement flow. It skips Git, npm, pip installation and installation checks, then starts a fresh Python interpreter with the original environment, working directory and startup arguments. The port and PID are retained. Installed packages and editable source are loaded from disk again. Git, Node.js and a Studio installation are not required for this mode. Workers managed by this service prevent restart unless `force=true` successfully stops them; foreign Runs in a shared workspace are ignored.

Restart records use `mode: restart` and the existing `get_update_status` Job, with phases `accepted`, `starting`, `succeeded` or `failed`. Success still requires the replacement server to start listening. Restart does not update another service's independent repository or Python environment, and does not coordinate services sharing installed files.

## Admission and restart

By default, worker Runs managed by this service prevent updating or restarting. Runs started by another service or CLI in a shared workspace do not block this service restart and are not cancelled. Managed workers that have published terminal metadata but have not exited still need to stop. Coordinate Git/pip updates when other services share the source tree or Python environment. `force=true` cancels exact managed Runs before admission; a managed Run whose termination cannot be confirmed prevents updating. Source/environment preflight happens before cancellation. Accepted updates enter maintenance: new local Jobs other than `version` and `get_update_status`, plugin mutations and Task submissions are rejected.

The invoking HTTP, SSE or MCP response finishes before shutdown begins. The application closes its streams, components and subprocesses normally. The stopped service replaces itself with a snapshotted standard-library updater, which performs the update and re-executes the original `axonx start` arguments from the original directory using the same interpreter. The process PID is retained, including under systemd or launchd. Custom embedded ASGI applications do not support automatic restart.

The service is unavailable while fetching, building, installing and restarting. Studio retries the status query every three seconds while visible, then offers **Reload Studio** after success. It cannot display new progress or logs during the outage. Service managers must allow the update duration; each external command has a 30-minute timeout, and its process group is cleaned up on completion, timeout or interruption.

## Durable results and failures

A successful update Job response means acceptance, not update completion. Save `answer.update_id`:

```bash
axonx get_update_status --update-id YOUR_UPDATE_ID
# Omit the ID to read the latest record
axonx get_update_status
```

The response contains `record` and a log tail of at most 64 KiB. Records include the update mode, phase, timestamps, before/after package versions, fetched commit and error. State and the executor snapshot live under `<workspace>/updates/<update_id>/`; protect this directory because the restart plan can contain startup arguments with credentials.

Phases are `accepted`, `fetching`, `cleaning`, `building`, `installing`, `verifying`, `starting`, `succeeded`, and `failed`. Success is recorded only after the replacement HTTP server has started listening. Interrupted records are marked failed on a later service startup.

Build, installation or verification failure records an error and attempts to start the service again. This is recovery of availability, not rollback: Git changes and partial pip changes remain. If imports or startup fail before the service can record the failure, inspect the persisted record and `update.log` locally. A later startup reconciles unfinished records. There is no automatic version rollback.

## MCP transport

The MCP endpoint now uses stateless Streamable HTTP with JSON responses. Clients must not rely on retained server sessions across calls or restarts.

Active scheduled Tasks are an exception to forced cancellation: queued or running schedule-origin Tasks owned by this service prevent Git updates, pip updates, and disk restarts even with `force=true`. Studio displays their schedule names and Task IDs and disables the action. The backend checks the same rule before cancelling any worker. Admission and Task worker launch share the environment-operation queue, so a concurrent schedule submission cannot slip between this check and maintenance.
