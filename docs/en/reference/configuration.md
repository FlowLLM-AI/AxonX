# Configuration Reference

![Configuration resolution](../../figures/reference/config-resolution.svg)

## Minimal override configuration

```yaml
extends: default
workspace_dir: /srv/axonx/workspace
log_dir: /srv/axonx/logs
timezone: Asia/Shanghai
language: en
service:
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
cron: []
```

```bash
axonx app --config app.yaml --service.host 127.0.0.1
```

## ApplicationConfig

Application fields are `workspace_dir`, `log_dir`, `timezone`, `execution_target`, `environment`, `command`, `app_name`, `bind_host`, `transfer_budget_bytes`, `language`, `enable_logo`, `log_to_console`, `log_to_file`, `targets`, `cron`, `components`, `jobs`, and optional `service`. Unknown top-level fields are rejected. Default transfer budget is 512 MiB; default language is `en` and timezone `Asia/Shanghai`. The startup layer provides `command` for service-owned CLI children.

Execution CLI options override the service's resolved `get_config`, then `ExecutionSettings` defaults. `get_config` includes absolute workspace/log directories, execution environment and resolved application configuration. It requires authentication and can contain environment values; treat its response as configuration data, not a public diagnostic report.

## Configuration discovery and inheritance

`ConfigLoader` supports YAML, YML and JSON. `--config` accepts a path, a bundled name (`default`, `remote`), or an installed `axonx.configs` entry point. A file with an extension resolves from the current working directory, then the built-in config directory. Named providers must be unique; ambiguity with built-ins is rejected.

`extends` accepts a parent name/path or ordered list. Existing relative parent files resolve against the declaring file. Mappings merge recursively; lists and scalar values replace inherited values. Cycles are rejected. A selected custom file does not implicitly inherit `default`; declare `extends: default` when needed.

## Environment expansion and paths

CLI startup loads `.env` from the working directory or parents without overriding existing environment variables. Configuration interpolation supports `${NAME}` and `${NAME:-default}`. General workspace/log paths resolve in the executing process; do not assume they are relative to the YAML file. Named configuration entry points locate data in their target package.

## ComponentConfig and named components

```yaml
components:
  task_index:
    default:
      backend: local
      poll_interval: 5
  machine:
    default:
      backend: local
```

The category selects a capability domain, `default` is an instance name, `backend` selects a provider. Current domains include agent, task_index, machine, proxy, sync and updater. Dependencies are declared with a typed base and an instance name. Jobs, service and steps are configured through their own fields. Configure Cron with the top-level `cron` field.

## JobConfig

Jobs support `backend` (default `pipeline`), `description`, JSON object `parameters`, `enable_serve`, `enable_stream`, `requires_auth`, `steps`, and `defaults`. Step provider options remain separate from public arguments. System-injected fields are validated separately and cannot be supplied by callers. Extra backend options are retained by ComponentConfig. Public availability depends on both serving flags and authentication configuration.

## CronConfig

```yaml
cron:
  - expression: "0 16 * * 1-5"
    command: "axonx exec --task download_tushare_task --days-back 7"
```

Only five numeric cron fields and local `axonx exec --task NAME` commands are supported by CLI startup. Commands are tokenized without a shell; client options are rejected. Lists replace inherited schedules. Triggers use application timezone, do not replay missed occurrences and require restart to reload. See [Scheduling](../guides/scheduling.md).

## TargetConfig

```yaml
targets:
  - address: http://node-b:1024
    token: ${NODE_B_TOKEN}
```

Addresses require an explicit port and are normalized. Duplicates and unknown fields are rejected. Backend forwarding resolves only configured targets and their credentials. Explicit CLI targets connect directly using CLI credentials; they need not appear in the local service's list.

## HTTP service

`service.backend: http` exposes Jobs, events, MCP, `/upload` and optionally Studio. Common fields include `host` (falling back to `bind_host`), `port`, `token`, `web_enabled`, `shutdown_timeout` and `cleanup_timeout`. The foreground daemon has a separate total 5-second exit limit after Ctrl+C or SIGTERM, even if `cleanup_timeout` is longer. Configure a token to expose authenticated capabilities. Proxy routes use upstream authentication. See [Authentication](../guides/authentication.md) and [Deployment](../guides/deployment.md).

Sources: [models](../../../axonx/app/config/models.py), [loader](../../../axonx/app/config/loader.py), [defaults](../../../axonx/app/config/default.yaml).
