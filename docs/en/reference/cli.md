# CLI Reference

## Command responsibilities

| Command                 | Where it runs              | Result                                  |
| ----------------------- | -------------------------- | --------------------------------------- |
| `axonx`, `--help`, `-h` | Local, offline             | CLI syntax                              |
| `app`                   | Local daemon and service   | Foreground service supervision          |
| `exec --task NAME`      | Current CLI process        | Business output JSON and Task exit code |
| `kill --task-id ID`     | Current CLI environment    | Final Task metadata after termination   |
| `plugin …`              | Current Python environment | Plugin metadata or installation result  |
| Any configured Job name | Selected service           | `JobResponse` JSON or event stream      |

An explicit `--target HOST:PORT` sends native commands (`app`, `exec`, `kill`, `plugin`) to the service's `cli` Job. The remote CLI rejects `app`, nested `cli`, and forwarding to another target. Ordinary Jobs connect directly to the selected service.

## Capability discovery and environment diagnosis

```bash
axonx help
axonx help --job cli
axonx diagnose
axonx exec
axonx list_task_defs --include-schemas false
axonx get_task_def --task demo
```

Bare `exec` lists Tasks in the current interpreter without contacting a service. Definition Jobs describe the persistent service's catalog. New CLI processes rediscover installed plugins; restart a persistent service to reload its registration snapshot and cached classes.

## Startup and configuration overrides

```bash
axonx app --config default
axonx app --config app.yaml --service.port 2024
```

Dotted options build nested mappings. Configuration supports `extends`, recursive mapping merges and whole-list replacement. See [Configuration](configuration.md).

## Task execution and observation

```bash
axonx exec --task demo --task-name check --x 1 --y 2
axonx status --task-id 'base#demo#check' --detail full
axonx wait_task --task-id 'base#demo#check' --client-timeout 600
axonx kill --task-id 'base#demo#check' --timeout 5 --force false
```

`exec` is synchronous. Without a service it can fall back to execution defaults; authentication, protocol and failed `get_config` responses are errors. Shared options are `workspace_dir`, `log_dir`, `timezone`, `execution_target`, `log_to_console`, `log_to_file` and `environment.KEY`. Precedence is explicit CLI options > service `get_config` > defaults. Explicit environment keys merge with the returned execution environment.

For remote execution, add `--target HOST:PORT` and set `AXONX_TARGET_TOKEN`. The native command streams stdout/stderr and preserves the target process exit code. `--client-timeout` controls the connection, not the Task's business deadline. With the default cli Job, interrupting a remote command request stops observation while execution continues. Use kill to stop the Task; service shutdown also terminates its manual command groups. Inspect metadata before retrying.

## Lightweight query defaults

CLI `status` and `wait_task` request `detail=summary`; file previews default to 20 rows / 8192 bytes; Agent lists and history default to 20 items. Explicit options override these defaults. Job defaults may differ; inspect `help --job NAME`.

## Parameter and value conversion

Use `--field value` pairs. Hyphens become underscores, dots create nested dictionaries. Values convert booleans, nulls, numbers, JSON arrays/objects and JSON-quoted strings. Quote Task IDs containing `#` and JSON arrays in the shell. Use `--upstream-task-ids '["etl#name#instance"]'` to declare dependencies; this does not execute upstream Tasks. CLI `exec` also accepts comma-separated upstream IDs.

## Client options

`--target`, `--token`, `--client-timeout`, `--stream`, and `--stream-format` are connection/presentation fields, separate from Job arguments. The default timeout is 60 seconds. Targets require an explicit port and may use HTTP(S); paths, query strings and embedded credentials are rejected. CLI tokens default to `AXONX_SERVICE_TOKEN` locally and `AXONX_TARGET_TOKEN` for an explicit target. Python clients require an explicit token.

## Stream output

```bash
axonx stream_task --task-id 'base#demo#check' --stream true --stream-format json
axonx agent_chat --message 'Inspect the workspace' --stream true
```

Ordinary Jobs default to a single response. Streaming uses `/jobs/NAME/events`; `blocks` is human-readable, `json` emits one event per line. The terminal `result` event carries `success`, `answer` and `metadata`. Native remote commands stream their process output regardless of `--stream`.

## Plugin subcommands

```bash
axonx plugin list
axonx plugin show DISTRIBUTION
axonx plugin inspect ./plugins/qlib_a158
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
axonx plugin install -e ./plugins/qlib_a158
axonx plugin uninstall DISTRIBUTION
```

With `--target`, paths are evaluated on the target. Local files are not transferred automatically. For local-to-remote deployment, explicitly build a wheel, upload it, install its returned absolute `location`, and clean up its returned relative `path`. See [Plugin deployment](../plugins/management.md). Editable installation requires a source directory on the executing machine; it cannot be combined with `--output`.

## Output and exit codes

Successful Jobs return 0, failed Jobs 1. Input errors return 2, other CLI failures 1. `exec` returns the Task exit code and prints its business output. Native remote commands preserve exit status, mapping negative signal status to `128 + signal`. HTTP success alone does not prove Task success.

## Service self-update

Use `update_from_git`, `update_from_pip`, `restart_service` and `get_update_status` as configured. They require a daemon-backed service and authentication. They take no `force` argument. See [Self-update](../guides/operations.md#service-updates-and-restart).
