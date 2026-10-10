---
title: "External Agents: Skill and CLI"
description: Develop quantitative plugins with Skill + prompt and execute experiments through CLI or MCP.
---

# External Agents: Skill and CLI

External Agents use their own models, code tools, and session environments to develop or improve quantitative plugins, then execute and inspect research through AxonX. This guide uses CLI access; read [MCP integration](mcp-integration.md) when the host needs to discover service tools directly.

![External Agent development and research workflow](../../figures/agent/external-workflow.svg)

## Prepare the service and instructions

Start a service with the [quickstart](../getting-started/quickstart.md), install research plugins in the execution service's Python environment, and prepare data. Remote plugins and workspaces need separate preparation; see [remote machines](../guides/remote-machines.md). An agent using the CLI needs access to the `axonx` command.

The repository provides an [AxonX Skill](../../../skills/axonx/SKILL.md) for contract discovery, submission and waiting, evidence inspection, and plugin development. Load it using the host's supported Skill mechanism; installation directories and configuration differ among hosts.

The Skill uses absolute documentation and source URLs, so it can be copied independently. Its example source paths refer to the root of an AxonX checkout. For code development, provide a checkout and file/command tools; installing the Python package alone does not supply the example plugin sources. You can also have the Agent read the [development and operations guide](../dev_guide.md) directly.

The external host manages model credentials; the AxonX service token authenticates research service access. Use configured credentials without putting tokens into prompts or research reports.

## Verify connections and Task definitions

The default local service reads its token from `AXONX_SERVICE_TOKEN`:

```bash
axonx version
axonx machine_status
axonx plugin list
axonx get_task_definition --task demo
```

Without a target, `plugin list` queries the current Python environment. If CLI and service environments differ, specify the service address explicitly to query its plugins and configure the corresponding `AXONX_TARGET_TOKEN`.

For direct remote access:

```bash
export AXONX_TARGET_TOKEN='<target service token>'
axonx version --target 192.0.2.10:1024
axonx machine_status --target 192.0.2.10:1024
axonx plugin list --target 192.0.2.10:1024
axonx get_task_definition --task demo --target 192.0.2.10:1024
```

Replace the example address. Direct access does not require a local service. An explicit `--target` defaults to `AXONX_TARGET_TOKEN` even when it points to the local machine. See [client configuration](../reference/client-configuration.md) for full connection rules.

## Complete an execution and inspect evidence

```bash
axonx submit --task demo --x 2 --y 3 --target 192.0.2.10:1024
```

Keep the actual `answer.task_id` and `answer.run_id`, check `success`, and wait for that execution:

```bash
axonx wait_task --task-id '<task_id>' --run-id '<run_id>' \
  --client-timeout 120 --target 192.0.2.10:1024
axonx status --task-id '<task_id>' --target 192.0.2.10:1024
axonx read_task_log --task-id '<task_id>' --target 192.0.2.10:1024
axonx get_task_context --task-id '<task_id>' --target 192.0.2.10:1024
```

Confirm the terminal state is `succeeded`, then inspect metadata and its declared artifacts. A successful query means the query worked; a successful submission means it was accepted. Neither replaces Task success. Use [workspace-relative paths](../guides/workspace-files.md) for files; paginated previews do not represent the complete dataset.

Omit `task_name` by default so the framework generates an instance name. Reusing an explicit name replaces a finished task's records and artifacts; see [task lifecycle](../concepts/task-lifecycle.md).

## Give the agent a concrete research goal

```text
Read the AxonX Skill and the baseline plugin source. Develop a separate plugin or optimize the named existing plugin.
Define the hypothesis and fixed controls, implement the quantitative code, and test feature timing and artifact compatibility.
Install into the selected service, discover live Task schemas, and execute the required research stages.
Keep actual Task/Run IDs; inspect artifacts and report comparable metrics, failures, and limitations.
Use development windows for candidate selection and reserve an independent confirmation window.
```

Feature changes usually require ETL → Train → Predict → Backtest. Model changes can reuse a compatible ETL; portfolio-management changes can reuse a compatible Predict. Run factor analysis independently from ETL when diagnostics are needed. After changes to contracts, fields, or feature timing, verify whether old upstream artifacts remain reusable.

Define controls and confirmation windows with [experiment design and confirmation](../research/experiments.md) before agent development experiments. See the [project benchmark](../../../README.md#benchmark-agent-developed-market-cross-sectional-features) and [Qlib Factor](../../../plugins/qlib_factor/README.md) for the concrete case and evidence; see the [README development workflow](../../../README.md#agent-access-and-development-guides) for an example exploration prompt.

## What to report on completion

Report the execution target, actual Task/Run IDs, terminal state, parameters, artifact locations, and metrics and definitions supporting the conclusion. For failures, report actual errors and completed stages. State the inspection scope when execution is pending or complete artifacts were unavailable.

Follow the [contribution guide](../../../CONTRIBUTING.md) and [Task contracts](../reference/task-contracts.md) during implementation. See the [CLI reference](../reference/cli.md) for command fields and [MCP integration](mcp-integration.md) for tool discovery and response handling.
