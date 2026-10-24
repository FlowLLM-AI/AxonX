# Quick start

Install AxonX in Python 3.12+:

```bash
pip install 'axonx[studio]'
axonx exec --task demo --task-name quickstart --x 2 --y 3
```

The built-in Demo requires no market-data or model credentials. It runs synchronously without a resident service, prints its output and returns exit code 0 on success. The Task ID is `base#demo#quickstart`; metadata is under `.axonx/base/base#demo#quickstart/metadata.json` with the default configuration. Use a fresh name to retain another experiment.

## Start the observation service

Use the same working directory, workspace and log configuration as the execution process:

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx start --service.host 127.0.0.1
```

Keep this terminal open. In another terminal with the same environment and token:

```bash
axonx version
axonx status --task-id 'base#demo#quickstart' --detail full
axonx read_task_log --task-id 'base#demo#quickstart'
```

The default service address is `http://127.0.0.1:1024`. Studio displays existing Task records and read-only Task definitions. Status comes from Task-written metadata. Independent local exec does not depend on service availability, and the service does not repair interrupted records or control those processes.

## Research plugins

Install the required plugin in the execution environment, prepare its data and inspect its input schema before running `axonx exec --task <registration>`. Preserve parameters, data windows, Task/Run IDs, costs and artifact references. Task success does not prove research improvement.

[Task execution and observation](../guides/task-management.md) · [Plugin management](../plugins/management.md) · [Research workflow](../research/workflow.md)
