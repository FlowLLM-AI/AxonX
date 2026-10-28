# Machine, Configuration and Maintenance API

Inspect the selected interpreter, machine and application. Diagnostic output reports credential presence rather than credential values.

All Jobs below use `POST /jobs/NAME` with `{"arguments": {...}}`. Streams use `/jobs/NAME/events`; MCP uses the same Job name and business arguments. Discover the target schema with `help --job NAME`. Replace example Task/session IDs with actual values.

## Endpoint list

| Job                 | Purpose                                                                                                                                                    |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `help`              | List public Jobs on this service, or inspect one Job's input and output schemas. CLI connection options such as --target are separate from Job parameters. |
| `diagnose`          | Inspect this service's build, Python, workspace disk, resources and resource usage. Credential values are never returned.                                  |
| `version`           | Return the installed AxonX version.                                                                                                                        |
| `get_config`        | Return this service's resolved application configuration, including schedules, execution defaults and environment. Execution directories are absolute.     |
| `list_machines`     | Check the health of all configured remote AxonX machines.                                                                                                  |
| `machine_status`    | Get local or remote AxonX machine status.                                                                                                                  |
| `python`            | Execute multiline Python code on the selected AxonX machine using the service's interpreter and installed packages in a fresh process.                     |
| `update_from_git`   | Stop the service, fast-forward the current branch from its upstream, build and install AxonX and Studio, then restart. Running scheduled Tasks continue.   |
| `update_from_pip`   | Stop the service, upgrade axonx and axonx-studio from the package index, then restart. Running scheduled Tasks continue.                                   |
| `restart_service`   | Restart the application and reload its configuration and schedules; stop manual commands and preserve scheduled Tasks.                                     |
| `get_update_status` | Read an update record and log tail; omit update_id for the latest update.                                                                                  |

## help

List public Jobs on this service, or inspect one Job's input and output schemas. CLI connection options such as --target are separate from Job parameters.

| Argument | Type     | Required | Default / constraints |
| -------- | -------- | -------- | --------------------- |
| `job`    | `string` | no       | `{"minLength":1}`     |

```json
{
  "arguments": {
    "job": "cli"
  }
}
```

## diagnose

Inspect this service's build, Python, workspace disk, resources and resource usage. Credential values are never returned.

No business arguments.

```json
{
  "arguments": {}
}
```

## version

Return the installed AxonX version.

No business arguments.

```json
{
  "arguments": {}
}
```

## get_config

Return this service's resolved application configuration, including schedules, execution defaults and environment. Execution directories are absolute.

No business arguments.

```json
{
  "arguments": {}
}
```

Returns resolved application/execution configuration, including absolute execution directories and environment. It can contain environment values. Authentication is required.

## list_machines

Check the health of all configured remote AxonX machines.

No business arguments.

```json
{
  "arguments": {}
}
```

## machine_status

Get local or remote AxonX machine status.

No business arguments.

```json
{
  "arguments": {}
}
```

## python

Execute multiline Python code on the selected AxonX machine using the service's interpreter and installed packages in a fresh process.

| Argument  | Type     | Required | Default / constraints                               |
| --------- | -------- | -------- | --------------------------------------------------- |
| `code`    | `string` | yes      | `{"minLength":1}`                                   |
| `timeout` | `number` | no       | `{"exclusiveMinimum":0,"maximum":300,"default":30}` |

```json
{
  "arguments": {
    "code": "print(1 + 2)",
    "timeout": 30
  }
}
```

Executes source in a fresh service-side interpreter process, not a persistent Python session. Returns stdout/stderr, exit_code and truncation information. Restrict source to the requested operation.

## update_from_git

Stop the service, fast-forward the current branch from its upstream, build and install AxonX and Studio, then restart. Running scheduled Tasks continue.

No business arguments.

```json
{
  "arguments": {}
}
```

## update_from_pip

Stop the service, upgrade axonx and axonx-studio from the package index, then restart. Running scheduled Tasks continue.

No business arguments.

```json
{
  "arguments": {}
}
```

## restart_service

Restart the application and reload its configuration and schedules; stop manual commands and preserve scheduled Tasks.

No business arguments.

```json
{
  "arguments": {}
}
```

## get_update_status

Read an update record and log tail; omit update_id for the latest update.

| Argument    | Type     | Required | Default / constraints          |
| ----------- | -------- | -------- | ------------------------------ |
| `update_id` | `string` | no       | `{"pattern":"^[0-9a-f]{32}$"}` |

```json
{
  "arguments": {}
}
```

## Maintenance results

Update/restart responses report acceptance and an update_id. Query get_update_status after reconnection; successful acceptance is not completion. Manual service-owned commands stop with the service, daemon-owned scheduled Tasks continue. No force input is accepted. See [Self-update](../guides/self-update.md).

Source: [Default Job contracts](../../../axonx/app/config/default.yaml) · [Job protocol](overview.md)
