# Frequently Asked Questions

When investigating a problem, first distinguish service connectivity, Job calls, and background Task execution. A successful HTTP request does not mean background computation succeeded; see [Troubleshooting](guides/operations.md) for the full process.

## Why Do Lists Fail to Load Even Though Studio Opens?

The static frontend can load independently, but APIs still require an online backend. Check `/health`, the development proxy address, and server logs. With Vite, restart after changing `AXONX_DEV_SERVER`. See [Getting Started with Studio](getting-started/studio.md).

## Why Do /health or /jobs Return 401?

After a service token is configured, these protocol endpoints also require a Bearer token. Enter the local service token in Studio settings; use the corresponding client configuration for the CLI. Do not confuse a remote machine token with the local service token. See [Client Configuration](reference/client-configuration.md).

## Why Can I See the Catalog but Not Find a Particular Job?

The public catalog comes from configured Jobs, rather than all Python methods. Jobs requiring authentication may be filtered out when no service token is configured; functionality may also be unavailable if an optional component is disabled. Consult `/jobs` and the [Configuration Reference](reference/configuration.md).

## Why Are There No Results After submit Returns?

`submit` returns `task_id`, `run_id`, and `task`, indicating that submission was accepted. Then call `wait_task`, `status`, or check the runtime center. Bind waiting to this run_id to avoid reading another execution after a fixed-name rerun. See [Submission and Observation](guides/task-management.md).

## What Is the Difference Between Task ID and run_id?

Task ID identifies a task directory in the workspace; run_id identifies one execution. Rerunning a terminal task with the same name replaces its directory, so the directory is not an immutable historical archive. See [Task Concepts](concepts/task-lifecycle.md).

## Does Setting source_tasks Automatically Execute Upstream Tasks?

No. It records source relationships for context and relationship graphs. Upstream tasks must still run first and produce the files required downstream. Separate multiple Task IDs with commas; see [Task Relationship Graphs](concepts/task-lineage.md).

## Why Are Alpha158 Training or Backtest Tasks Missing?

Research plugins provide them; installing the core package alone does not guarantee their availability. Check installed plugins and task definitions first, then prepare data using the [Research Workflow](research/workflow.md). An enumerated type does not imply an implementation is currently available.

## Why Does a Local Python Change Not Take Effect in the Worker?

Check how the plugin is installed and which Python environment it uses. Use editable installation during development; restart persistent services as required by your changes to refresh registrations. Background workers are separate processes. See the [Plugin Guide](plugins/management.md).

## Why Do Backtest Returns and Curve Interpretations Differ?

First check whether you are using net or gross returns, transaction costs, and common valid trading days. A plugin's open positions, signal targets, and actual holdings also use different definitions. See [Backtesting](research/backtest.md) and [Strategy Comparison](research/strategy-comparison.md).

## What If File Preview Fails or Does Not Show All Content?

Confirm that the path is relative to the workspace, then check file existence, format, and preview row limits. Preview is a bounded read, rather than a complete download. Obtain complete artifacts from the execution machine's workspace; continue table previews with supported pagination parameters. See the [Workspace Guide](guides/workspace-files.md).

## Why Does Remote Execution Report Connection or Permission Errors?

When forwarding through Studio or the outer HTTP target, check that the target is in the server's targets configuration; direct CLI --target connections do not require this configuration. Then check remote service reachability and target token matching. Studio forwards through the local backend rather than managing all remote credentials directly from the page. See the [Machine Guide](guides/remote-machines.md).

## Why Are Raw Data or Agent Sessions Still Missing After Task Synchronization?

Synchronization is an optional component. Task synchronization focuses on terminal task directories; it does not copy raw data, plugin environments, or Agent workspaces. Prepare the target environment separately; see the [Synchronization Guide](guides/task-sync.md).

## Why Can I Not Chat on the Agent Page?

Check the Agent component, SDK, model environment, and available tools. Agent sessions are distinct from Tasks; the end of a request does not necessarily mean a background Task it triggered has completed. See [Agent Configuration](agent/configuration.md) and the [Usage Guide](agent/usage.md).

## What Is the Difference Between Cancellation and Deletion?

Cancellation stops a task that is executing; deletion removes task records and artifacts. Use task_id to cancel the current execution, or run_id to cancel one exact execution. Run-based cancellation never targets a newer execution. Supplying both IDs checks that they match; a mismatched pair returns false. Do not delete directories as a substitute for runtime cancellation. See [Submission and Observation](guides/task-management.md).

## Next Steps

- Verify an environment from scratch: [Quickstart](getting-started/quickstart.md)
- Look up complete fields: [Task Protocol](reference/task-contracts.md)
- Look up API errors: [API Overview](api/overview.md)
- Contribute to development: [Development Guide](dev_guide.md)
