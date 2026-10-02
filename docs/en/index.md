# AxonX English Documentation

AxonX packages quantitative research capabilities as plugins, runs computations through Tasks, and provides unified entry points through Jobs, the CLI, Studio, and MCP.

![AxonX Studio overview](../figures/studio/home.png)

## Start Here

| Goal                          | Reading path                                                                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| First experience              | [Overview](../../README.md) → [Quickstart](getting-started/quickstart.md) → [Studio](getting-started/studio.md)                                   |
| Conduct quantitative research | [Research Workflow](research/workflow.md) → [Reading Results](research/results.md) → [Backtesting](research/backtest.md)                          |
| Call the service              | [API Overview](api/overview.md) → [Task API](api/tasks.md) → [CLI](reference/cli.md) / [Python](reference/python.md)                              |
| Connect an Agent              | [Agent Configuration](agent/configuration.md) → [Usage](agent/usage.md) / [MCP Integration](agent/mcp-integration.md)                             |
| Extend the project            | [Development Guide](dev_guide.md) → [Plugin Protocol](reference/plugin-manifest.md) → [Framework Extensions](development/framework-extensions.md) |

The built-in demo requires no external data or model credentials. Research plugins, remote machines, Agent, and synchronization each have configuration prerequisites; prepare them using the relevant guides.

## Documentation Contents

### Getting Started

- [AxonX overview](../../README.md)
- [Quickstart](getting-started/quickstart.md)
- [Getting Started with Studio](getting-started/studio.md)

### Core Concepts

- [Architecture Overview](concepts/architecture.md)
- [Jobs and Tasks](concepts/jobs-and-tasks.md)
- [Task Identity and Lifecycle](concepts/task-lifecycle.md)
- [Task Dependencies and Lineage](concepts/task-lineage.md)
- [Workspace and Persistent Records](concepts/workspace.md)

### Operations and Deployment

- [Authentication and Permission Boundaries](guides/authentication.md)
- [Service Deployment and Studio Hosting](guides/deployment.md)
- [HTTP Upstream Proxy](guides/http-proxy.md)
- [Log Troubleshooting, Backup, and Recovery](guides/operations.md)
- [Using Remote Machines](guides/remote-machines.md)
- [Scheduled Jobs](guides/scheduling.md)
- [Task Submission and Management](guides/task-management.md)
- [Task Snapshot Synchronization](guides/task-sync.md)
- [Workspace Browsing and Preview](guides/workspace-files.md)

### Quantitative Research

- [Reading Backtest Results](research/backtest.md)
- [DingTalk Notifications](research/notifications.md)
- [Reading Research Results](research/results.md)
- [Strategy Comparison](research/strategy-comparison.md)
- [Tushare Data Downloads](research/tushare.md)
- [Quantitative Research Workflow](research/workflow.md)

### Plugins

- [Plugin management](plugins/management.md)
- [Alpha158](../../plugins/a158/README.md)
- [Alpha158 Enhanced](../../plugins/a158_enhanced/README.md)

### Agent

- [Claude Agent Configuration](agent/configuration.md)
- [MCP Integration for External Agents](agent/mcp-integration.md)
- [Using Agent](agent/usage.md)

### APIs and Events

- [Agent API](api/agent.md)
- [SSE Event Protocol](api/events.md)
- [Machine API](api/machines.md)
- [API Protocol Overview](api/overview.md)
- [Plugin and Synchronization API](api/plugins-sync.md)
- [Task API](api/tasks.md)
- [Workspace and File Transfer API](api/workspace.md)

### Configuration and Protocol Reference

- [CLI Reference](reference/cli.md)
- [Client and Connection Configuration](reference/client-configuration.md)
- [Server Configuration Reference](reference/configuration.md)
- [Plugin Packages and Contribution Protocol](reference/plugin-manifest.md)
- [Python Call Reference](reference/python.md)
- [Research Artifacts and Studio Display Protocol](reference/research-artifacts.md)
- [Task Input/Output and Persistence Protocol](reference/task-contracts.md)

### Development and Extensions

- [Contributing](../../CONTRIBUTING.md)
- [Framework Extensions](development/framework-extensions.md)
- [Extending Studio](development/studio.md)

### Other Entry Points

- [Development Guide](dev_guide.md): Task development workflow and practices.
- [FAQ](faq.md): connection, task, artifact, plugin, and Agent questions.

## Reading Conventions

The text, screenshots, and SVGs use English. Credentials and identifiers in examples are placeholders; screenshots retain only demonstration areas without private information.

Parameters, defaults, and response structures are based on the current source code. For the Tasks installed in a specific environment, consult the task definition catalog. Start with [Troubleshooting and Recovery](guides/operations.md) when problems arise.
