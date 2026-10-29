# Agent Development

AxonX gives Agents tools to develop research plugins, execute experiments, and inspect evidence. Choose a host, prepare its tools and execution service, then define the research objective.

![External and built-in Agent paths and the shared research loop](../../figures/agent/workflow.svg)

## Choose a path

|                     | External agent                                                      | Built-in agent                                                 |
| ------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------- |
| Entry point         | Hosts such as Codex or Claude Code                                  | Studio → Agent, or the `agent_chat` Job                        |
| Model configuration | Managed by the external host                                        | Server-side Claude Agent SDK configuration                     |
| AxonX connection    | Direct CLI access or service `/mcp`                                 | Built-in component invokes configured Jobs through Dispatcher  |
| Instructions        | [AxonX Skill](../../../skills/axonx/SKILL.md) and development guide | Optionally load the development guide bundled with the package |
| Tool scope          | Available CLI commands or public service MCP catalog                | `job_tools`, SDK tools, and permission settings                |
| Session records     | Managed by the external host                                        | Managed by AxonX session storage                               |

External integration does not require `CLAUDE_CODE_*` settings or built-in guide loading. The built-in Agent loads the development guide by default and uses its CLI instructions; the in-process `job_tools` bridge is optional. The public external MCP catalog may include queries, file changes, and the `cli` command Job. Task execution, stopping, and plugin installation use its `exec`, `kill`, and `plugin` commands. Actual capabilities depend on the selected path's configuration and schemas.

## Prepare the environment

1. Provide an AxonX source checkout and the plugin to change. A package installation alone does not include example plugin sources.
2. Ask the Agent to read the [AxonX Skill](../../../skills/axonx/SKILL.md), or install it using the host's supported mechanism. The built-in Agent can also load the bundled [development and operations guide](../dev_guide.md).
3. Supply file and command tools with source access. Configure the built-in Agent's `cwd`, SDK tools, and guide loading separately; see [configuration](configuration.md).
4. Select an execution service and prepare its plugins, dependencies, and data. Keep the same target for installation, submission, waiting, and queries.

External hosts configure their own models; the service configures the built-in model. Configure the AxonX service token and model credentials separately.

Start with the [quickstart](../getting-started/quickstart.md). The Skill uses absolute source URLs and can be copied independently; example source paths refer to the checkout root. Keep tokens out of prompts and reports.

## Verify CLI access

An Agent using CLI needs the `axonx` command. For a remote service, set `AXONX_TARGET_TOKEN` and use the same `--target` throughout. Without a target, `plugin list` describes the CLI interpreter; with a target it queries that service. See [connections](../guides/deployment.md#remote-connections) and [client configuration](../reference/client-configuration.md).

```bash
axonx version --target 192.0.2.10:1024
axonx get_task_def --task demo --target 192.0.2.10:1024
axonx exec --task demo --task-name agent-check --x 2 --y 3 --target 192.0.2.10:1024
axonx status --task-id 'base#demo#agent-check' --detail full --target 192.0.2.10:1024
```

Replace the example address. Exec waits and prints business output. Check exit code, Task state and `started_at`; inspect the record before retrying a disconnected command, since cancellation can stop its owned process.

## Research prompt

```text
Read the AxonX Skill and qlib_a158 source. Develop a separate research plugin
to investigate whether residual volatility and downside risk improve Alpha158 ranking.

Use only information available at signal time. Fix the data snapshot, labels,
sample filters, training parameters, windows, and costs for feature comparisons.
First specify development and independent confirmation windows and the candidate
selection rule; identify missing prerequisites before execution.

Implement and test the quantitative code, register the plugin, then install it
in the selected execution service. Discover that service's actual Task schemas,
check upstream compatibility, and run ETL, training, prediction, and backtesting,
waiting for each upstream execution to succeed.

Keep the source revision, data settings, parameters, costs,
actual Task IDs and metadata `started_at`.
Report RankIC, net returns, drawdown, turnover, failures, and evidence limits.
Lock the candidate before independent confirmation and propose the next change
based on the evidence.
```

You can instead specify training performance or portfolio policy improvements. Feature changes usually rerun the complete chain; model changes can reuse compatible ETL; portfolio changes can reuse compatible predictions. Reuse depends on actual Task schemas, fields, feature order, and artifact protocols.

## The shared research loop

1. Define the research objective and controls; provide the Skill, source checkout, and code tools.
2. Develop or optimize the plugin, validate the code, and install it in the selected execution service.
3. Discover live Task schemas, check upstream compatibility, and execute the required stages.
4. Record each Task ID and metadata `started_at`, and verify upstream success before the next stage.
5. Inspect artifacts and compare results; use the evidence to guide further code or parameter changes.

Keep the same `--target` across stages when using direct CLI access. Studio forwards requests through its same-origin backend to the selected machine. Tasks, data, and plugins live in the execution service's environment; agent integration does not migrate them automatically.

## Verification and next steps

Keep source changes, execution-service installation, and Task submission separate. Passing code checks verifies implementation; research metrics and independent confirmation determine whether improvement claims are supported. Task success establishes completed execution.

See the [development and operations guide](../dev_guide.md) for implementation, [Alpha158 workflow](../research/workflow.md) for stage commands, [experiment design](../research/experiments.md) for comparisons, and the [Alpha158 case study](../research/alpha158-case.md) for a complete example.

Report the execution target, Task IDs and start times, terminal states, parameters, artifacts, metrics and evidence limits. Built-in setup and session operations are covered in [configuration](configuration.md) and [usage](usage.md); external tool discovery is covered in [MCP integration](mcp-integration.md).
