# CLI reference

Without `--target`, start, exec, and plugin run locally, while other actions call the local service. An explicit `--target` sends the original command arguments to the remote `cli` Job, which starts `python -m axonx.cli` without a shell and forwards stdout, stderr, and the exit code. Remote paths belong to that machine; its CLI working directory is the service workspace. Remote start and nested forwarding are rejected.

## Command responsibilities

| Command      | Execution location                     | Purpose                                                                     |
| ------------ | -------------------------------------- | --------------------------------------------------------------------------- |
| axonx start  | Current process                        | Start the daemon and its service/cron workers                               |
| axonx exec   | Current process or explicit target     | Execute a synchronous Task; list the catalog when no arguments are supplied |
| axonx JOB    | Connected service                      | Ordinary or streaming Job invocation                                        |
| axonx plugin | Current environment or explicit target | Plugin inspection, building, installation, and uninstallation               |
| axonx help   | Connected service                      | Discover public Jobs; inspect schemas with `--job NAME`                     |

Local exec does not require a running service; remote CLI does. Process isolation does not constitute a security sandbox.

## Capability discovery and environment diagnosis

```bash
axonx
axonx help --target node-b:1024
axonx help --job python --target node-b:1024
axonx diagnose --target node-b:1024
```

No arguments print local usage without a service. Top-level `--help` and `-h` have been removed. `help` remains a service Job; `--job NAME` returns a public Job schema. Remote CLI forwarding requires the target service to expose the authenticated `cli` Job. `diagnose` reports build, Python, workspace, resources, installed plugins, and credential-presence booleans.

## Startup and configuration overrides

```bash
axonx start
axonx start --config app.yaml
axonx start --config default --cron research
axonx start --config app.yaml --service.port 2024 --service.web-enabled false
axonx start --workspace-dir .axonx --log-dir logs
```

Without --config, the resolver reads default. See [Server configuration](configuration.md) for configuration inheritance, environment expansion, and merging. Remote `start` is not supported; `exec --target HOST:PORT` runs synchronously on that service machine.

`--cron` accepts a built-in/installed name or an explicit `.cron` file, sharing configuration lookup with its own `axonx.crons` entry-point group. It enables local five-field `axonx exec --task` scheduling. See [Scheduling](../guides/scheduling.md).

## Task execution

```bash
axonx exec
axonx exec --task demo --task-name cli-demo --x 1 --y 2
```

Local exec runs synchronously without an HTTP service, prints Task output and returns its exit code. The Task writes metadata under the configured workspace. The observer service must read that same workspace. Use terminal or process-manager facilities for background execution.

```bash
axonx status --task-id 'base#demo#cli-demo' --detail full
axonx wait_task --task-id 'base#demo#cli-demo' --run-id '<run_id from metadata>'
```

The service exposes Task observation without dedicated submit, cancel or delete Tasks Jobs. Remote `exec --target HOST:PORT` remains a synchronous remote CLI command: disconnecting its request or stopping that service terminates its process.

## Lightweight query defaults

| Query                                      | CLI default                                             | Explicit detail                                                              |
| ------------------------------------------ | ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `list_task_statuses`                       | Summaries, across all transports                        | `--detail full`; filter with `--task-type` and `--state`                     |
| `status`, `wait_task`                      | Summary with Task/Run ID, state, progress and ownership | `--detail full` for inputs, outputs, children, artifacts and complete errors |
| `list_installed_task_definitions`          | Registration metadata, without generating schemas       | `--include-schemas true`, or one `get_task_definition`                       |
| `read_task_log`                            | Last 8,192 bytes                                        | Explicit `--limit` (at most 262144); bind `--run-id`                         |
| `preview_file`                             | 20 rows; text/Markdown/JSON/YAML byte budget 8,192      | `--limit` (at most 5000), `--max-bytes` (at most 33554432)                   |
| `list_agent_sessions`, `get_agent_session` | 20 records                                              | Explicit `--limit` and `--offset`                                            |

These intentional query-default changes do not alter task execution or persisted records. HTTP/MCP `status`/`wait_task` still default to full snapshots; Task catalog schemas remain enabled for those transports. A truncated structured preview returns a marked UTF-8 prefix without parsing incomplete JSON/YAML; inspect `truncated` and `parse_error`. CSV/JSONL/Parquet use row pagination, independently of `max_bytes`.

```bash
axonx status --task-id 'base#demo#cli-demo' --detail full
axonx list_task_statuses --detail full --state failed
```

To confirm startup, poll `status`, match the returned Run ID and check `queued`/`running` plus logs. `wait_task` waits for a terminal state; a short client timeout is not a startup check and does not cancel the Task. On transport errors, keep the original IDs and query before retrying submission. HTTP errors identify the exception type, target, endpoint and configured timeout; the HTTP timeout is a per-operation/inactivity limit, not a total Task deadline.

## Parameter and value conversion

Parameters must be supplied as pairs; booleans also require values. Hyphens become underscores, and dots create nested dictionaries.

CLI natural-value conversion recognizes null/none, booleans, integers/floats, and JSON in that order, then retains strings. Numbers beginning with zero avoid direct numeric conversion; for example, 000001 remains a string. Wrap valid JSON objects and arrays in single quotes, using double quotes inside JSON.

To force numeric text to remain text, use a JSON string:

```bash
axonx agent_chat --message '"123"'
```

The actual message here is the string 123; `--message 123` becomes a number and fails a string Schema. An empty string can be written as `--path ''`; quoting is recommended for #, spaces, and JSON. Repeated fields, conflicts between parent and nested fields, missing values, `key=value`, and `--field=value` are not valid ordinary Job parameter syntax.

## Client options

| Option           | Default                                   | Meaning                                |
| ---------------- | ----------------------------------------- | -------------------------------------- |
| --target         | null; connects locally on 1024 by default | Connect directly to the target service |
| --token          | null                                      | Explicit Bearer token                  |
| --client-timeout | 60                                        | Request budget; must be greater than 0 |
| --stream         | false                                     | Use the SSE endpoint                   |
| --stream-format  | blocks                                    | blocks or json                         |

Client options may appear before or after ACTION but cannot be repeated; they are excluded from Job arguments.

```bash
axonx --target node-b:1024 version --token your-target-token
axonx version --target node-b:1024 --client-timeout 120
```

Without an explicit token, AXONX_SERVICE_TOKEN is read when no target is specified; AXONX_TARGET_TOKEN is read with an explicit target. See [Client connection configuration](client-configuration.md).

## Stream output

```bash
axonx stream_task --task-id 'base#demo#cli-demo' \
  --stream true --stream-format blocks --client-timeout 600
axonx agent_chat --message 'Check the task statuses in the current workspace' \
  --stream true --stream-format json --client-timeout 600
```

Control local exec processes through their execution environment. The service exposes no Task cancellation or deletion interface. Disconnecting read-only observation does not change an independent Task execution.

Use `--task-id` for the current execution, or `--run-id` for one exact execution. At least one ID is required; when both are supplied, a mismatched pair returns false.

## Plugin subcommands

plugin uses argparse subcommand syntax, including positional arguments and the boolean `-e` switch; it is a separate exception to the ordinary paired Job-option rules.

```bash
axonx plugin list
axonx plugin show axonx-example
axonx plugin inspect ./plugins/example
axonx plugin inspect ./dist/axonx_example-0.1.0-py3-none-any.whl
axonx plugin build ./plugins/example --output ./dist
axonx plugin install ./plugins/example
axonx plugin install -e ./plugins/example
axonx plugin uninstall axonx-example
```

Without a target, plugin operations address the current Python environment. With a target, all plugin subcommands run on that machine, including build and editable install. Paths and `--output` refer to that machine. `-e` cannot be combined with `--output`.

Build local source first, upload the wheel with `POST /upload`, then install the returned absolute `location`:

```bash
axonx plugin list --target node-b:1024
axonx plugin install /srv/axonx/.axonx/tmp/upload-id/example.whl \
  --target node-b:1024 --client-timeout 300
```

Upload and installation are separate; installation does not remove the input file. It changes site-packages without refreshing loaded service objects or tracking restart requirements. Concurrent environment mutations are not coordinated. See [Plugin management](../plugins/management.md).

## Output and exit codes

| Exit code | Situation                                                                                |
| --------- | ---------------------------------------------------------------------------------------- |
| 0         | JobResponse.success=true or a local operation succeeds                                   |
| 1         | Business failure or connection/runtime error; exec may use the Task's specific exit code |
| 2         | FileNotFoundError, KeyError, TypeError, or ValueError in the main CLI; parameter errors  |

Ordinary Jobs print complete JSON; exec prints Task output rather than JobResponse. On failure, stderr may contain `Error: Type: message`. Scripts should check exit codes and retain the full response to distinguish submission failure from a subsequent task failure.

## Remote CLI protocol

`POST /jobs/cli/events` accepts `{"arguments":{"argv":["exec","--task","demo","--x","1","--y","2"]}}`. Output arrives as `log` events with `channel=stdout` or `stderr`; the final result contains `stdout`, `stderr`, `exit_code`, and truncation flags. The ordinary JSON endpoint keeps at most 1 MiB per captured channel; streaming forwards all output. The CLI replays the output and returns the child's exit code without wrapping its JSON again. Set `--client-timeout` for long operations; output is not a keepalive.

Task execution and process control belong to the CLI execution environment. The service reads published metadata through TaskRepository and does not cancel, recover or adopt Task processes.

## Related documentation

- [Quickstart](../getting-started/quickstart.md)
- [Task API](../api/tasks.md)
- [Plugin management](../plugins/management.md)
- [Existing development quick reference](../dev_guide.md)

Implementation references: `axonx/cli/parser.py`, `main.py`, `constants.py`, `plugin_kit/cli.py`.

## Service self-update

[Service self-update](../guides/self-update.md)
