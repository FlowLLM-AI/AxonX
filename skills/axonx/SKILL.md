---
name: axonx
description: Use AxonX for quantitative research, research plugin development, task submission and tracking, and inspection of logs, dependencies, and artifacts. Use when the request involves AxonX Tasks or research workflows.
---

# AxonX

Use the AxonX repository's maintained guides to develop research plugins and operate Tasks through the CLI or configured MCP tools.

## Documentation

This skill requires an AxonX source checkout. Resolve the links below relative to this file, and resolve paths in each guide relative to that guide. Run repository-relative commands from the repository root. If this skill has been copied elsewhere, locate the user's AxonX checkout and read the corresponding documents there before executing commands.

- Read the relevant sections of the [development and operations guide](../../docs/en/dev_guide.md) for Task implementation, plugin registration, submission, and CLI commands. The [Chinese guide](../../docs/zh/dev_guide.md) covers the same workflow.
- For MCP access, read [MCP integration](../../docs/en/agent/mcp-integration.md) to understand available tools and response handling. Use the connected service's actual tool schemas.
- For research comparisons, read [strategy comparison](../../docs/en/research/strategy-comparison.md) and [backtest interpretation](../../docs/en/research/backtest.md).
- For code changes, follow the checkout's [AGENTS.md](../../AGENTS.md) and [contribution guide](../../CONTRIBUTING.md). For framework extension work, read [framework extensions](../../docs/en/development/framework-extensions.md).

Keep detailed command examples and contracts in these guides; read only the sections needed for the current request.

## Operate Tasks

1. Establish the execution service and workspace from the user's request and configuration. Keep the same target for plugin queries, Task submission, status, logs, and artifact inspection. Example addresses in the guides are placeholders. Use configured authentication without exposing tokens.
2. Discover installed plugins and registered Task names using `axonx plugin list`; inspect inputs and outputs with `axonx get_task_definition --task <registered_name>`. For remote operations, use the same `--target` on supported commands. Check machine resources before submission.
3. Select only the stages needed for the requested experiment. Reuse successful upstream artifacts: factor changes usually require ETL → Train → Predict → Backtest; model changes can reuse ETL; position-management changes can reuse Predict. Run Analysis when factor diagnostics are needed.
4. Submit with schema-defined parameters and actual successful upstream Task IDs. Omit `--task-name` unless the user requests an explicit name: reusing a name replaces artifacts after the previous execution finishes.
5. Inspect the complete response's `success` and `answer`. Submission acceptance is not execution success. Record the returned `task_id` and `run_id`; never construct them from examples. Use both IDs with `wait_task` to track that execution.
6. Continue tracking while the state is `queued` or `running`. Only submit dependent stages after `succeeded`. For `failed` or `cancelled`, inspect errors and logs before deciding whether a retry is appropriate. A successful status query does not mean the Task succeeded.
7. Inspect result metadata and the artifacts it identifies on the execution service. Report the target, actual Task and Run IDs, final state, relevant artifact locations, and evidence supporting the research conclusion. If execution remains pending or inspection is incomplete, say so.

Use destructive Jobs and `shell` only when required by the user's task and the execution target is established. Plugin installation changes the selected environment; perform it when required for the requested work.

## Develop Research Plugins

Keep research algorithms in plugins and reuse framework Task contracts. Define typed input/output parameters, a nonempty Task class docstring describing purpose, inputs, and artifacts, and the plugin registration and package entry point described in the guide. Populate all required output fields and use workspace/task path helpers for artifacts.

Installation and submission are separate operations. After installation, verify registration and the Task schema on the execution service before running the affected stages. Preserve task identity, lifecycle, persisted records, artifact formats, and resource cleanup unless the user requests a compatibility change.

For experiment comparisons, keep data, date windows, and other parameters consistent while changing the factor being evaluated. Check costs and trading assumptions before interpreting differences in backtest results.
