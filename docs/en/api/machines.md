# Machine API

Query versions, the health of configured targets, and machine resources, or execute commands on the selected service machine. target belongs to the HTTP request envelope or CLI connection options, rather than these Jobs' business fields.

![Machine API call flow](../../figures/api/machine-target.svg)

## Calling conventions

All endpoints below use `POST /jobs/{name}` with a `{"arguments":{...}}` request body. For remote forwarding, add `target` at the envelope's top level, outside arguments. Every response uses [JobResponse](overview.md#responses-and-errors). Table defaults come from the current built-in configuration and Steps. Deployments may change Job Schemas; the running service's `/jobs` is authoritative.

All JSON examples illustrate structure; replace task IDs, session IDs, file paths, and hashes with values actually returned by your service. See [Task contracts](../reference/task-contracts.md) for the complete shared TaskStatus fields.

## Endpoint list

| Job              | Purpose                                                                        |
| ---------------- | ------------------------------------------------------------------------------ |
| `version`        | Read the installed package version.                                            |
| `list_machines`  | Check the health of all configured targets.                                    |
| `machine_status` | Sample service-machine resources.                                              |
| `python`         | Execute multiline Python code using the selected service’s Python environment. |

## version

Read the installed package version.

No public business parameters; use `{"arguments":{}}`.

**Request**

```json
{
  "arguments": {}
}
```

**Response**

answer is a version string; metadata.version also provides that version.

```json
{
  "answer": "0.1.0",
  "success": true,
  "metadata": { "version": "0.1.0" }
}
```

**Behavior and failure cases**

The version value is only an example; use machine_status to inspect build branch/commit information.

## list_machines

Check the health of all configured targets.

No public business parameters; use `{"arguments":{}}`.

**Request**

```json
{
  "arguments": {}
}
```

**Response**

answer is an array of MachineHealth, each containing address and healthy.

```json
{
  "answer": [
    {
      "address": "http://node-b:1024",
      "healthy": true
    }
  ],
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

The default targets=[] produces an empty result. healthy=false may indicate a network, token, or service problem; it does not imply insufficient resources.

## machine_status

Sample service-machine resources.

No public business parameters; use `{"arguments":{}}`.

**Request**

```json
{
  "arguments": {}
}
```

**Response**

answer is MachineInfo: axonx, cpu, memory, and gpus.

```json
{
  "answer": {
    "axonx": {
      "version": "0.1.0",
      "git_commit": null,
      "git_branch": null
    },
    "cpu": {
      "total_cores": 8,
      "physical_cores": 4,
      "usage_percent": 12.0
    },
    "memory": {
      "total_bytes": 16000000000,
      "used_bytes": 4000000000,
      "available_bytes": 12000000000,
      "usage_percent": 25.0
    },
    "gpus": []
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

The cpu fields total_cores/physical_cores may be null; memory is measured in bytes. GPU vendor is limited to nvidia/amd. The list may be empty when detection commands are unavailable or no devices exist; Apple GPU detection is not guaranteed.

## python

Execute Python source on the selected service machine in a fresh subprocess using the service's interpreter (`sys.executable`) and installed packages. Source is sent through stdin without command-line length limits. Each call has independent Python variables, inherits the service's working directory and environment, and runs with the service user's permissions.

| Parameter | Type   | Required | Default       | Constraints and meaning                                                  |
| --------- | ------ | -------- | ------------- | ------------------------------------------------------------------------ |
| `code`    | string | Yes      | `— (omitted)` | Python source, including newlines; minLength=1. Print results to stdout. |
| `timeout` | number | No       | `30`          | Execution timeout in seconds; exclusiveMinimum=0, maximum=300.           |

Call `POST /jobs/python` with:

```json
{
  "arguments": {
    "code": "from pathlib import Path\nprint(Path.cwd())",
    "timeout": 30
  }
}
```

MCP clients pass `code` as an ordinary multiline string using the discovered schema. JSON requires its usual string escaping. CLI example: `axonx python --code 'print(1 + 1)' --timeout 30`. Use the `target` envelope field or CLI `--target` for remote execution.

**Response**

`answer` is PythonOutput: stdout, stderr, exit_code, stdout_truncated, and stderr_truncated. `success` is true when execution completes within the timeout with exit code zero.

```json
{
  "answer": {
    "stdout": "/srv/axonx\n",
    "stderr": "",
    "exit_code": 0,
    "stdout_truncated": false,
    "stderr_truncated": false
  },
  "success": true,
  "metadata": {}
}
```

**Behavior and failure cases**

Each output stream retains at most 1 MiB; excess output is discarded and the corresponding truncation flag is set. Python exceptions and syntax errors return `success=false`, a nonzero `exit_code`, and an error in `stderr`. Timeout returns `success=false`, `exit_code=null`, and a timeout explanation in `stderr`, preserving captured output. Timeout or cancellation kills the process group, closes the input/output pipes, and reaps the main process without waiting for detached descendants to close inherited pipes.

The default built-in Agent's `job_tools` list does not expose `python`. Add it to `components.agent.default.job_tools` when enabling Python execution for that Agent; external MCP exposure follows the service's Job catalog.

## Failure response examples

A nonzero Python exit or timeout is a business failure returned through the normal protocol. For `code="import sys; sys.exit(3)"`:

```json
{
  "answer": {
    "stdout": "",
    "stderr": "",
    "exit_code": 3,
    "stdout_truncated": false,
    "stderr_truncated": false
  },
  "success": false,
  "metadata": {}
}
```

On timeout, exit_code=null and stderr includes `Command timed out after ... seconds`. timeout=0 or timeout>300 returns HTTP 422 during Schema validation. One target with healthy=false in list_machines does not automatically fail the entire query; interpret each machine's result separately.

## Related documentation

- [Protocol, authentication, and errors](overview.md)
- [Remote machines](../guides/remote-machines.md)
- [CLI reference](../reference/cli.md)
- [Event protocol](events.md)

Implementation references: `axonx/config/default.yaml`, `axonx/steps/machine/` and `axonx/components/service/http/jobs.py`.
