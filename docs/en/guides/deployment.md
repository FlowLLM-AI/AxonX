# Service deployment and Studio hosting

A minimal deployment consists of a Python service, workspace, and optional Studio package on one machine. Make the authenticated API available first, then install Studio and configure process supervision. The process supervision and HTTPS examples below require adaptation to your system.

## Installation and configuration

The source environment requires Python 3.12 or later; Studio builds require Node.js 22.13+ (22.x), 24.x, or 26+. Install from the repository root:

```bash
uv sync
uv run axonx help
```

Create `server.yaml`:

```yaml
extends: default
workspace_dir: /srv/axonx/workspace
log_dir: /srv/axonx/logs
service:
  backend: http
  host: 127.0.0.1
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
  shutdown_timeout: 1
  web_enabled: true
```

The absolute directories are Linux examples, not the project's default paths. Ensure the service user can read and write the workspace and logs, and install required plugins in the same environment.

```bash
export AXONX_SERVICE_TOKEN='<separate service token>'
uv run axonx start --config server.yaml
```

For direct connections from other machines, change host to `0.0.0.0` and configure network access. The default configuration already listens on this address; the example uses loopback for an external reverse proxy.

## Verify the API

```bash
curl -fsS 'http://127.0.0.1:1024/health' \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"
uv run axonx version
uv run axonx list_installed_task_definitions
```

After configuring a token, health also requires a Bearer header. Health means the service responds; it does not prove the model SDK, external data sources, or every plugin works. Continue with demo to verify submission and waiting.

## Install and host Studio

```bash
python -m pip install axonx-studio
```

Restart the service to load pages from the Studio Python package. Without Studio, only page hosting is skipped; the API continues to work. `web_enabled: false` disables page hosting without affecting Job, MCP, or file interfaces.

For source deployments, run `npm ci` and `npm run build` in `axonx_studio/`, then `python -m pip install ./axonx_studio` from the repository root. Vite's development server is for frontend development; see [Getting started with Studio](../getting-started/studio.md).

## Example background process supervision

Linux can use systemd. This is a minimal unit example; replace paths, account, and virtual environment:

```ini
[Unit]
Description=AxonX service
After=network.target

[Service]
Type=simple
User=axonx
WorkingDirectory=/srv/axonx/source
EnvironmentFile=/etc/axonx/service.env
ExecStart=/srv/axonx/source/.venv/bin/axonx start --config /etc/axonx/server.yaml
Restart=on-failure
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

service.env stores required environment variables and should have restricted read permissions. On macOS, use your own launchd configuration; the repository does not provide a complete system-service installer.

## HTTPS and event streams

The built-in Uvicorn service has no TLS configuration. Terminate HTTPS at an external entry such as Caddy or Nginx, then proxy to the loopback HTTP address; clients should explicitly use the public HTTPS URL.

The proxy should preserve Authorization, request bodies, and correct paths; SSE entry points should allow long-lived connections and avoid response buffering. MCP and `/files` must also reach the same backend, and upload entry limits should match actual artifact sizes.

External entry timeouts, built-in shutdown_timeout, TaskManager terminate_grace_seconds, and client timeout serve different purposes: proxy waiting, service request shutdown, worker termination grace, and call waiting, respectively.

## Updates and shutdown

Configuration, Jobs, and plugin contributions load during application assembly. Restart the service after changes and check that version, plugin list, Task Schemas, and Studio assets have matching versions.

Normal service shutdown stops managed workers and records the corresponding runs as cancelled. Restarting does not automatically resume these research tasks. Before upgrades during long training, wait for completion or confirm that the plugin provides usable recovery.

For migration, stop writes first, copy the workspace, logs, and configuration, restore a matching plugin environment, then check historical records and artifacts. Do not copy only Python packages while overlooking experiment files.

[Authentication](authentication.md) · [Operations and recovery](operations.md) · [Configuration reference](../reference/configuration.md) · [Plugin management](plugin-management.md)

Source: [HTTP service](../../../axonx/components/service/http/service.py), [Studio directory discovery](../../../axonx/components/service/http/studio.py), [TaskManager shutdown](../../../axonx/components/task_manager/local/manager.py).
