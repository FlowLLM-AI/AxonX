# Service self-update

A service started with `axonx start` can update its backend and Studio through authenticated Jobs. In Studio, open **Run → Environment → Update service** on the selected machine. Set the service token before using this feature; update Jobs are hidden on unauthenticated services.

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

## Admission and restart

By default, active Tasks prevent updating. `force=true` cancels exact managed Runs before admission; an active Run whose termination cannot be confirmed prevents updating. Source/environment preflight happens before cancellation. Accepted updates enter maintenance: new local Jobs other than `version` and `get_update_status`, plugin mutations and Task submissions are rejected.

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
