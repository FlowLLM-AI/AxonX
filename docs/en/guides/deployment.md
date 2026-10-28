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

`axonx restart_service` reloads source, `.env`, Task definitions and Cron configuration. `update_from_git` and `update_from_pip` start a fresh service after updating. The daemon PID stays the same and the service PID changes. Supervisor-source or startup-argv changes require stopping and relaunching the whole `axonx app`. See [Service updates](self-update.md).

Normal service shutdown stops Cron admission, closes components and terminates service-owned manual CLI children; daemon-owned scheduled exec processes continue. The first Ctrl+C or SIGTERM begins shutdown; `cleanup_timeout` bounds the total duration. Another Ctrl+C or timeout forces exit. Forced termination may leave running metadata: observation does not rewrite it; subsequent execution identity checks or explicit kill settle confirmed exited processes. Service restarts do not rerun existing scheduled Tasks or replay missed slots.

Coordinate all writers before migration, then copy the workspace, configuration and required logs and restore the plugin environment.

Implementation: [daemon](../../../axonx/daemon/supervisor.py), [deployment stop tool](../../../scripts/stop_daemon.py), [HTTP service](../../../axonx/app/components/service/http/service.py).
