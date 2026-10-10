# AxonX Documentation Map

AxonX is an agent-native harness for quantitative research, providing unified tools and a runtime for quantitative code development, experiment execution, and result analysis. You define the research question; the Agent implements it; the Harness manages execution and evidence.

The reference research plugins adapt [Microsoft Qlib](https://github.com/microsoft/qlib)’s Alpha158 baseline, adding selectable factors and portfolio policies. AxonX also supports new research methods through plugins.

## Choose your starting point

| Goal                         | Start here                                                                                     | Outcome                                                         |
| ---------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Use AxonX for the first time | [Quickstart](getting-started/quickstart.md) → [Studio](getting-started/studio.md)              | Submit a demo, wait for success, and inspect records            |
| Develop with an Agent        | [Agent development](agent/overview.md) → [Skill and research prompt](agent/research-prompt.md) | Prepare source, tools, and an objective for plugin development  |
| Run a research baseline      | [Research](research/overview.md) → [Alpha158 workflow](research/workflow.md)                   | Connect data, training, prediction, and backtesting             |
| Implement a research plugin  | [Development and operations guide](dev_guide.md) → [Plugin management](plugins/management.md)  | Implement Tasks, install and discover the plugin                |
| Evaluate a change            | [Experiment design](research/experiments.md) → [Alpha158 case](research/alpha158-case.md)      | Compare candidates, retain evidence, and identify limits        |
| Manage execution services    | [Operations](guides/overview.md)                                                               | Track Tasks, manage files and remote environments               |
| Look up fields and protocols | [Reference](reference/overview.md)                                                             | Find interfaces, configuration, and extension contracts         |
| Change AxonX itself          | [Contributing](development/overview.md)                                                        | Extend the framework or Studio and complete contribution checks |

Read the [project overview](../../README.md) for positioning, plugins, and a case summary. The built-in demo needs no market data or model credentials. Research plugins need data; the built-in Agent needs service-side model configuration; external Agents use their host's model configuration.

## Recommended reading order

Complete the demo first, then read about [Jobs and Tasks](concepts/jobs-and-tasks.md), [lifecycle](concepts/task-lifecycle.md), [workspace](concepts/workspace.md), and [lineage](concepts/task-lineage.md). See [architecture](concepts/architecture.md) for implementation principles.

The main research path is: **connect an Agent → define an objective → develop a plugin → install in the execution service → run Tasks → inspect artifacts → compare and iterate**. Agent development covers hosts, tools, and prompts; Research covers algorithm examples, plugin authoring, and evaluation; Contributing covers framework and Studio changes.

Each page has one navigation owner and cross-links to related steps. How-to guides explain procedures, Reference defines fields and contracts, plugin READMEs maintain algorithms, and case studies retain settings, metrics, reproduction commands, and Task provenance.

## Reading conventions

English and Chinese pages use matching paths and share screenshots and diagrams. Replace example addresses, credentials, and Task IDs with actual values. Use the Job and Task schemas discovered on the connected service.

Accepted submission still requires waiting for a terminal Task state. Lineage records do not automatically schedule a DAG. Reusing a name replaces a finished task directory; preserve distinct identities for experiment comparisons.

Start with the [FAQ](faq.md) when something fails, then use [troubleshooting and recovery](guides/operations.md) to locate the failure in the service, Job, or Task layer.
