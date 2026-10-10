# AxonX Documentation Map

AxonX is an agent-native harness for financial quantitative research. Plugins provide algorithms, Tasks define research inputs and outputs, and the framework manages execution, records, and artifacts. Researchers, external agents, and scripts use the same Jobs and workspace records through Studio, CLI, or MCP.

## Choose your starting point

| Goal                            | Start here                                                                                      | What you will be able to do                                         |
| ------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Use AxonX for the first time    | [Quickstart](getting-started/quickstart.md) → [Studio](getting-started/studio.md)               | Submit a demo, wait for completion, inspect parameters and results  |
| Conduct quantitative research   | [Research overview](research/overview.md) → [Research workflow](research/workflow.md)           | Prepare data and connect ETL, training, prediction, and backtesting |
| Research with an external agent | [Agent integration overview](agent/overview.md) → [External agents](agent/external.md)          | Operate a research service through a Skill, CLI, or MCP             |
| Chat in Studio                  | [Built-in agent configuration](agent/configuration.md) → [Built-in agent usage](agent/usage.md) | Query tasks, troubleshoot, and explain existing research evidence   |
| Deploy services or manage tasks | [Operations overview](guides/overview.md) → [Remote machines](guides/remote-machines.md)        | Track execution, manage files, and connect to target services       |
| Develop plugins or client code  | [Development overview](development/overview.md) → [Task contracts](reference/task-contracts.md) | Implement research Tasks, register plugins, and call services       |

Read the [project overview](../../README.md) for positioning and the experiment case study. The built-in demo needs no market data or model credentials. Research plugins need data; the built-in agent needs model configuration; external agents use their host's model configuration.

## How the documentation is organized

### Get started: complete a minimal execution loop

Run a real task with the [quickstart](getting-started/quickstart.md), then inspect the same workspace in [Studio](getting-started/studio.md). Read about [architecture](concepts/architecture.md), [Jobs and Tasks](concepts/jobs-and-tasks.md), [task lifecycle](concepts/task-lifecycle.md), [lineage](concepts/task-lineage.md), and the [workspace](concepts/workspace.md) to understand submission, execution, and persistent records.

### Research: move from data to inspectable conclusions

Start with the [research overview](research/overview.md). The [research workflow](research/workflow.md) and [Tushare guide](research/tushare.md) cover data preparation and stage execution. [Reading results](research/results.md) covers artifact inspection. [Experiment design and confirmation](research/experiments.md), [backtest methodology](research/backtest.md), and [strategy comparison](research/strategy-comparison.md) explain how to evaluate evidence.

[Plugin management](plugins/management.md) covers installation, discovery, and deployment. [Alpha158](../../plugins/qlib_a158/README.md) provides the baseline research chain; [Qlib Factor](../../plugins/qlib_factor/README.md) provides a concrete case of added features and ablations; [Qlib Strategy](../../plugins/qlib_strategy/README.md) adds rank retention and bounded replacements. Plugin documentation owns algorithm parameters and experiment numbers.

### Agent: choose an external host or built-in sessions

The [integration overview](agent/overview.md) explains prerequisites for each path. [External agents](agent/external.md) covers research with a Skill and CLI; [MCP integration](agent/mcp-integration.md) explains service tool discovery and responses. [Built-in configuration](agent/configuration.md) and [usage](agent/usage.md) cover Claude Agent SDK sessions in Studio.

### Operations: maintain services and execution environments

The [operations overview](guides/overview.md) connects service setup and record maintenance. Daily operations include [task management](guides/task-management.md), [file browsing](guides/workspace-files.md), and [task snapshot synchronization](guides/task-sync.md). For deployment, read [authentication](guides/authentication.md), [service hosting](guides/deployment.md), and [remote machines](guides/remote-machines.md). Configure an [HTTP proxy](guides/http-proxy.md), [scheduled Jobs](guides/scheduling.md), or [DingTalk notifications](research/notifications.md) as needed. See [operations](guides/operations.md) for troubleshooting, backup, and recovery.

### Reference: look up parameters and responses

Choose an interface in the [reference overview](reference/overview.md). Use the [CLI reference](reference/cli.md) for command syntax, [Python reference](reference/python.md) for programmatic calls, and [client configuration](reference/client-configuration.md) and [server configuration](reference/configuration.md) for connection and startup fields.

Start with the [API overview](api/overview.md), then consult [tasks](api/tasks.md), [events](api/events.md), [files](api/workspace.md), [machines](api/machines.md), [plugins and synchronization](api/plugins-sync.md), or [agent sessions](api/agent.md).

### Developers: implement capabilities and preserve contracts

Choose an extension layer in the [development overview](development/overview.md). The [contribution guide](../../CONTRIBUTING.md) covers development setup and checks; the [development and operations guide](dev_guide.md) covers Task implementation and CLI practice. [Framework extensions](development/framework-extensions.md) and [Studio development](development/studio.md) explain their respective extension points. Consult [Task contracts](reference/task-contracts.md), the [plugin protocol](reference/plugin-manifest.md), and [research artifact contracts](reference/research-artifacts.md) during implementation.

## Reading conventions

How-to guides address concrete goals; reference pages define fields, responses, and boundaries. Project and plugin READMEs maintain the project overview and algorithm details respectively. English and Chinese pages use matching paths and share English screenshots and diagrams.

Replace example credentials, addresses, and Task IDs with actual values. Use the Job and Task schemas discovered on the connected service. Accepted submission still requires waiting for a terminal Task state. Reusing a name replaces a finished task directory; preserve distinct identities for experiment comparisons.

Start with the [FAQ](faq.md) when something fails, then use the [operations guide](guides/operations.md) to locate the failure in the service, Job, or Task layer.
