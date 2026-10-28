# Quickstart

Use Python 3.12+ on macOS or Linux. Start with the bundled Demo before installing research plugins.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install 'axonx[studio]'
axonx --help
```

`axonx` alone installs the backend; the `studio` extra adds the prebuilt UI. Research plugins are installed separately from this repository.

## Configure and start the service

Set a service token in the startup directory's `.env` or shell, then start the application:

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

The default port is `1024`, workspace `.axonx`, and timezone `Asia/Shanghai`. The foreground daemon supervises the application service. Keep this terminal open; use another terminal with the same Python environment and token for subsequent commands. Open `http://127.0.0.1:1024` for Studio.

The startup logo and service console output appear in this terminal and are also saved to `.axonx/daemon/<identity>/service.log`, including after service restarts. Ctrl+C stops the daemon and service, including service-owned manual CLI commands, with a total shutdown limit of 5 seconds. Already launched scheduled commands continue independently; future schedule triggers stop.

## Discover and execute Demo

```bash
axonx help
axonx list_task_defs --include-schemas false
axonx get_task_def --task demo
axonx exec --task demo --task-name quickstart --x 1 --y 2
```

`exec` waits for completion, prints the business output as JSON, and returns the Task exit code. Demo returns the sum `3`. Its Task ID is `base#demo#quickstart`. Choose another `task_name` to retain an independent result.

## Wait and inspect results

```bash
axonx status --task-id 'base#demo#quickstart' --detail full
axonx read_task_log --task-id 'base#demo#quickstart'
axonx get_task_graph --task-id 'base#demo#quickstart'
```

For a long-running execution, run observations in another terminal. `wait_task --task-id ID --client-timeout 600` waits for the current execution and rejects a change to its `started_at` during the wait. CLI status and wait default to summaries; request full detail for inputs and outputs. Queries do not repair stale records.

## Inspect persistent records

The current record is `.axonx/base/base#demo#quickstart/metadata.json`; it includes `started_at`, state, process identity, steps, input/output parameters and child invocations. Task states are `running`, `succeeded`, and `failed`. Logs live under the configured `log_dir`, referenced by metadata.

An explicit same-name rerun replaces current files after the previous execution has stopped; `persistent/` is retained. It is not an immutable run archive. Stop an active execution explicitly with `axonx kill --task-id ID`; see [Task management](../guides/task-management.md).

## Execute in the current process

`exec` uses CLI execution options, then service `get_config`, then built-in defaults. Only connection failures permit falling back to defaults. It can execute without a service; specify `--workspace-dir` when selecting a workspace. With `--target HOST:PORT`, the target's authenticated `cli` Job launches the command there; all paths belong to that machine.

## Next steps

- [Plugin installation and remote deployment](../plugins/management.md)
- [Research workflow](../research/workflow.md)
- [Built-in Agent](../agent/configuration.md)
- [Configuration](../reference/configuration.md)
