# Service deployment and Studio hosting

Use Python 3.12+ and a dedicated environment for the backend and optional Studio package. A daemon supervises one service; Cron runs inside the service. External process managers should own the `axonx app` daemon and let it manage the service child.

## Installation and configuration

```bash
python -m venv .venv
source .venv/bin/activate
pip install 'axonx[studio]'
```

Create `server.yaml`, adjusting paths for the deployment machine:

```yaml
extends: default
workspace_dir: /srv/axonx/workspace
log_dir: /srv/axonx/logs
service:
  host: 127.0.0.1
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
  shutdown_timeout: 1
  cleanup_timeout: 15
cron: []
```

```bash
export AXONX_SERVICE_TOKEN='<dedicated-service-token>'
axonx app --config server.yaml
```

Bind `0.0.0.0` and configure network access for direct remote connections. Workspace, logs and startup directories must be accessible. Install research plugins in the same Python environment. See [Scheduling](scheduling.md) for periodic Tasks.

## Verification

```bash
curl -fsS 'http://127.0.0.1:1024/health' \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"
axonx version
axonx list_task_defs --include-schemas false
axonx exec --task demo --task-name deployment-check --x 1 --y 2
axonx status --task-id 'base#demo#deployment-check'
```

Health verifies readiness; demo checks execution and observation. The API can run without Studio. Restart the service after installing Studio and open `http://127.0.0.1:1024/`.

## Remote connections

The target needs its own service, interpreter, plugins, data and workspace. CLI connects directly; Studio forwards through its backend.

### CLI direct connections

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx version --target node-b:1024
axonx plugin list --target node-b:1024
axonx exec --task demo --task-name remote-check --x 1 --y 2 --target node-b:1024
axonx status --task-id 'base#demo#remote-check' --detail full --target node-b:1024
```

Ordinary Jobs call the target directly. Native commands forward argv through cli. Exec waits and streams target stdout/stderr, preserving the target exit code. Retain target, Task ID and started_at for follow-up observations. Connection cancellation may stop the owned remote execution; inspect before retrying.

### Studio backend forwarding

Configure target address/token in the local service's targets list. Studio selects that machine and sends a transport-level target; the backend resolves its credential. Job arguments do not override routing credentials. Each target has independent state and Agent sessions.

### Remote files and plugins

All native command paths are interpreted at the target service workspace, including plugin install/build/inspect source paths. --target does not upload local files. Build a local wheel, upload to /upload, install the returned absolute location, clean relative path and restart the persistent service to refresh its Task catalog. See [Plugin deployment](../plugins/management.md).

### Connectivity, resources and termination

Use list_machines/machine_status/diagnose for observed resources; there is no automatic machine scheduling. For kill use the source execution_target and workspace_dir from metadata. A display replica cannot control the source process, and machine_id is not an address.

## Deploying from a checkout

Run `./scripts/deploy.sh [application options]` in the activated execution environment, for example `./scripts/deploy.sh --config server.yaml`. The script changes to the repository root, which is the base for relative configuration paths. Git, Python and Studio-supported Node.js/npm are required.

Using the same configuration resolution and service identity as `axonx app`, the script verifies the daemon lock, supervisor command and service parentage, then stops the selected daemon and service before changing source. It fast-forwards the current branch from its upstream, builds Studio, installs backend and Studio in editable mode, runs `pip check`, installs all three research plugins, then runs `axonx app` in the foreground with the supplied application options. It never selects arbitrary listeners by port for termination.

Shutdown or identity-check failure aborts before updating source. Pull/build/install failure stops deployment; repair the failure and start again. There is no automatic rollback. For systemd/launchd deployments, stop the daemon with that manager first and restart through the manager after deployment, so supervisors do not compete.

## Process supervision example

```ini
[Unit]
Description=AxonX daemon
After=network.target

[Service]
Type=simple
User=axonx
WorkingDirectory=/srv/axonx/source
EnvironmentFile=/etc/axonx/service.env
ExecStart=/srv/axonx/source/.venv/bin/axonx app --config /etc/axonx/server.yaml
Restart=on-failure
KillMode=process
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

Replace paths and account, and restrict environment-file access. This example targets the daemon with `KillMode=process`, allowing it to close the service without the manager terminating independent scheduled processes. Such Tasks can survive a full daemon stop and must be managed explicitly by Task identity. macOS can use a custom launchd configuration; the repository does not ship a complete system-service installer.

## HTTPS and event streams

Terminate TLS at an external reverse proxy. Preserve Authorization, bodies, duplicate headers and paths; support `/mcp`, `/upload` and long-lived SSE without buffering. Proxy/client timeouts, Uvicorn draining and total service cleanup are separate budgets.

## Updates and shutdown

`axonx restart_service` reloads source, `.env`, Task definitions and Cron configuration. `update_from_git` and `update_from_pip` start a fresh service after updating. The daemon PID stays the same and the service PID changes. Supervisor-source or startup-argv changes require stopping and relaunching the whole `axonx app`. See [Service updates](operations.md#service-updates-and-restart).

The foreground daemon displays new service console output, including the startup logo, while retaining it in `workspace_dir/daemon/<identity>/service.log`. Output continues across service restarts; launching a new daemon does not replay old logs.

Ctrl+C in the startup terminal, or SIGTERM sent to the daemon, stops the daemon and requests service shutdown. This stops Cron admission, closes components and terminates service-owned manual CLI children. Already launched daemon-owned scheduled commands continue independently. The daemon enforces a total 5-second shutdown limit from the first Ctrl+C or SIGTERM, including service cleanup, updater shutdown and console draining. At the deadline it kills remaining service/updater process groups and exits immediately. Repeated signals do not extend this deadline. This limit applies even if `cleanup_timeout` is longer; that setting still bounds service cleanup during service-only restarts. Forced termination may leave running metadata: observation does not rewrite it; subsequent execution identity checks or explicit kill settle confirmed exited processes. Service restarts do not rerun existing scheduled Tasks or replay missed slots.

Coordinate all writers before migration, then copy the workspace, configuration and required logs and restore the plugin environment.

Implementation: [daemon](../../../axonx/daemon/supervisor.py), [deployment stop tool](../../../scripts/stop_daemon.py), [HTTP service](../../../axonx/app/components/service/http/service.py).
