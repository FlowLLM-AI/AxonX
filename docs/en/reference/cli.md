# CLI reference

AxonX commands use `axonx ACTION --field value`. start, exec, plugin, and help are handled locally; other ACTION values are service Job names. Configure the connection token first, then choose a Job from the [public catalog](../api/overview.md).

## Command responsibilities

| Command      | Execution location                     | Purpose                                                                     |
| ------------ | -------------------------------------- | --------------------------------------------------------------------------- |
| axonx start  | Current process                        | Start the services in the configuration                                     |
| axonx exec   | Current process                        | Execute a synchronous Task; list the catalog when no arguments are supplied |
| axonx submit | Connected service's worker             | Submit asynchronously through the submit Job                                |
| axonx JOB    | Connected service                      | Ordinary or streaming Job invocation                                        |
| axonx plugin | Current environment or explicit target | Plugin inspection, building, installation, and uninstallation               |
| axonx help   | Current process                        | Syntax quick reference                                                      |

exec does not require a running service; submit does. Process isolation does not constitute a security sandbox.

## Startup and configuration overrides

```bash
axonx start
axonx start --config app.yaml
axonx start --config app.yaml --service.port 2024 --service.web-enabled false
axonx start --workspace-dir .axonx --log-dir logs
```

Without --config, the resolver reads default. See [Server configuration](configuration.md) for configuration inheritance, environment expansion, and merging. Client --target/--client-timeout options cannot be used with start or exec.

## Task execution and submission

```bash
axonx exec
axonx exec --task demo --x 1 --y 2
axonx exec --task demo --x 1 --y 2 --task-name local-demo

axonx list_installed_task_definitions
axonx get_task_definition --task demo
axonx submit --task demo --x 1 --y 2 --task-name cli-demo
```

submit outputs a standard JobResponse. Save answer.task_id and answer.run_id and replace the placeholder below:

```bash
axonx wait_task --task-id 'base#demo#cli-demo' \
  --run-id YOUR_RETURNED_RUN_ID --client-timeout 600
axonx status --task-id 'base#demo#cli-demo'
axonx read_task_log --task-id 'base#demo#cli-demo' --offset -1 --limit 65536
```

The final success of wait_task depends on whether the task succeeded. Successful submit means only that the task was accepted and started; it does not establish that metadata has been published. Rerunning with a fixed name replaces a terminal directory; active tasks cannot be overwritten.

## Parameter and value conversion

Parameters must be supplied as pairs; booleans also require values. Hyphens become underscores, and dots create nested dictionaries.

```bash
axonx submit --task demo --x 1 --y 2 --fail false
axonx start --service.port 2024
axonx delete_tasks --task-ids '["base#demo#cli-demo"]'
axonx delete_entries --paths '["tmp/example.txt"]'
```

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

blocks is suitable for terminal reading; json emits one event-model JSON value per line for programmatic processing. The final result's success determines the exit code. Interrupting the consumer does not cancel a background research Task; cancel explicitly:

```bash
axonx cancel --task-id 'base#demo#cli-demo'
axonx cancel --run-id '<run_id>'
```

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

Without an explicit target, plugin operations address the current Python environment and do not connect to the local HTTP service by default. With an explicit target, list, show, inspect, install, and uninstall address the service environment. For remote install, the client first builds/inspects the source directory or wheel, then uploads it.

```bash
axonx plugin list --target node-b:1024
axonx plugin install ./plugins/example --target node-b:1024
```

build is local only and cannot use a remote target. Editable installation supports only local source directories and cannot use target or output; an existing wheel cannot use output. The remote installation client timeout is at least 300 seconds. Task-only wheel updates through the remote installation Job apply to subsequent Task queries and submissions without restarting. Check restart_required: Components/Jobs and replaced dependencies can still require a service restart.

## Output and exit codes

| Exit code | Situation                                                                                |
| --------- | ---------------------------------------------------------------------------------------- |
| 0         | JobResponse.success=true or a local operation succeeds                                   |
| 1         | Business failure or connection/runtime error; exec may use the Task's specific exit code |
| 2         | FileNotFoundError, KeyError, TypeError, or ValueError in the main CLI; parameter errors  |

Ordinary Jobs print complete JSON; exec prints Task output rather than JobResponse. On failure, stderr may contain `Error: Type: message`. Scripts should check exit codes and retain the full response to distinguish submission failure from a subsequent task failure.

## Related documentation

- [Quickstart](../getting-started/quickstart.md)
- [Task API](../api/tasks.md)
- [Plugin management](../plugins/management.md)
- [Existing development quick reference](../dev_guide.md)

Implementation references: `axonx/cli/parser.py`, `main.py`, `constants.py`, `plugin_kit/cli.py`.
