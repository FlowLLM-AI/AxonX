<p align="center">
  <img src="axonx_studio/public/axonx-logo.svg" alt="AxonX" width="560" />
</p>

<p align="center"><strong>An agent-native harness for quantitative research.</strong></p>

<p align="center">
  English · <a href="README_ZH.md">简体中文</a><br />
  <a href="https://flowllm-ai.github.io/AxonX/en/">Website</a> ·
  <a href="https://flowllm-ai.github.io/AxonX/en/docs">Documentation</a> ·
  <a href="https://github.com/FlowLLM-AI/AxonX/issues">Issues</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue" alt="Python 3.12+" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-blue" alt="Apache License 2.0" /></a>
</p>

## What is AxonX?

AxonX connects research code, task execution, logs, and results in one workspace. It represents data processing, factor analysis, training, prediction, and backtesting as Tasks with explicit input and output contracts. CLI, Studio, and Agent access the same capabilities through Job interfaces.

Researchers can inspect how a result was produced, reuse upstream data, compare experiments, and let an Agent investigate tasks and artifacts. Plugin authors supply the research algorithms; AxonX provides the execution and inspection infrastructure. AxonX is currently in alpha.

## Why AxonX?

- **Reuse research code as Tasks.** Typed inputs and outputs make data, model, and artifact requirements explicit. → [Task contracts](https://flowllm-ai.github.io/AxonX/en/reference/task-contracts)
- **Execution you can inspect.** Submit Tasks to independent worker processes and follow status, progress, logs, and results. → [Task management](https://flowllm-ai.github.io/AxonX/en/guides/task-management)
- **Trace results back to their inputs.** Workspace records keep parameters, artifacts, and upstream Task IDs together so you can reuse datasets and inspect experiment differences. → [Task lineage](https://flowllm-ai.github.io/AxonX/en/concepts/task-lineage)
- **One workflow across CLI, Studio, and Agent.** Use scripts, browser forms and charts, or an assistant that reads task evidence through configured tools. → [Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio) · [Agent](https://flowllm-ai.github.io/AxonX/en/agent/usage)
- **Extend and run remotely.** Package research capabilities as plugins and explicitly choose a remote execution target. → [Plugins](https://flowllm-ai.github.io/AxonX/en/guides/plugin-management) · [Remote machines](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines)

## Studio

Studio provides task submission, run details, machine resources, workspace browsing, and research result views.

![AxonX Studio home](docs/figures/studio/home.png)

See [Getting started with Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio) for setup and connection instructions.

## Quick start

Requires **Python 3.12+**. The local TaskManager supports **macOS and Linux**. Install from source:

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Run your first Task

The built-in Demo adds two integers and needs no service, market data, or model credentials:

```bash
axonx exec --task demo --task-name first-demo --x 2 --y 3
```

The command prints Task output with `result` equal to `5`. Task records are stored under `.axonx/` in the current directory; logs use `logs/`. Use a different task name, or omit `--task-name`, to keep separate experiments: reusing a name replaces a finished Task directory.

### Submit through the service

In terminal A, choose a service token and start the local service:

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx start --service.host 127.0.0.1
```

In terminal B, activate the same environment and set the same token:

```bash
source .venv/bin/activate
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx get_task_definition --task demo
axonx submit --task demo --task-name submitted-demo --x 2 --y 3
```

Save `answer.run_id` from the submission response, then replace the placeholder below with that value:

```bash
axonx wait_task --task-id 'base#demo#submitted-demo' \
  --run-id '<actual returned run_id>' --client-timeout 120
axonx status --task-id 'base#demo#submitted-demo'
```

Submission success means the request was accepted. Wait for state `succeeded`; the status response should contain `result.result: 5`. The default service port is `1024`. See the [full quick start](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart) for configuration, logs, and persistent records.

### Open Studio

Install the Studio Python package:

```bash
python -m pip install axonx-studio
```

Restart the service in terminal A, keeping the same service token. Open <http://127.0.0.1:1024/> and enter that token in **Settings → Service token**. AxonX loads the UI from the Studio package and serves Studio and API from the same address.

## Research with an Agent

The built-in assistant uses the Claude Agent SDK and configured Job tools to inspect task status, logs, upstream relationships, and workspace artifacts. Configure the [Agent backend](https://flowllm-ai.github.io/AxonX/en/agent/configuration), then open **Agent** in Studio. Ordinary research Tasks can run without model credentials.

Give it specific Task IDs and questions, for example:

- “Check Task `<task_id>`'s status, tail logs, and upstream tasks. Explain where it failed and what to inspect next.”
- “Compare Backtest Tasks `<A>` and `<B>`: check their common date window and cost assumptions before explaining the results.”

External Agents can also connect to the service's Streamable HTTP MCP endpoint at `http://127.0.0.1:1024/mcp` using the service's Bearer token. Available tools depend on the service configuration. See [Agent usage](https://flowllm-ai.github.io/AxonX/en/agent/usage) and [MCP integration](https://flowllm-ai.github.io/AxonX/en/agent/mcp-integration) for tools and permissions.

## How it works

**CLI / Studio / external Agent → Job interfaces → Task execution → workspace records and artifacts.**

Jobs validate calls and coordinate framework capabilities. For research submission, the TaskManager starts a worker process and returns a run identifier; the Task writes status, logs, and outputs. Query Jobs and Studio then read those records. `axonx exec` runs a Task directly in the current process.

Research plugins supply the algorithms. Upstream Task IDs record relationships, while users or scripts organize stage-by-stage execution. See the [architecture](https://flowllm-ai.github.io/AxonX/en/concepts/architecture) for the component boundaries.

## Quantitative research and plugins

![AxonX research and execution overview](docs/figures/getting-started/overview.svg)

A typical research chain is **raw data → ETL → training → prediction → backtesting**, with factor analysis branching from ETL. Tasks record upstream IDs through `source_tasks`, so datasets and predictions can be reused across experiments. Users or calling programs submit each stage.

The core supplies Task contracts and runtime infrastructure. Research plugins implement factors, models, and backtesting logic:

| Plugin source | Purpose |
| --- | --- |
| [Alpha158](plugins/a158/) | Alpha158 research task implementations |
| [Alpha158 Enhanced](plugins/a158_enhanced/README.md) | Extended Alpha158 research tasks and experiment guidance |

Start with the [research workflow](https://flowllm-ai.github.io/AxonX/en/research/workflow) for plugin installation and data prerequisites. Market-data and Agent features need their own provider configuration. See [Interpreting backtests](https://flowllm-ai.github.io/AxonX/en/research/backtest) for return definitions, costs, and trading assumptions.

Studio reads the resulting artifacts to display training metrics, predictions, and backtest summaries. For example, the backtest view shows overall signal metrics alongside period summaries:

![AxonX Studio backtest overall metrics](docs/figures/studio/backtest-overall.png)

This screenshot illustrates an existing experiment's result view. See [Research results](https://flowllm-ai.github.io/AxonX/en/research/results) for how to read each stage's outputs.

## Documentation

| I want to… | Guide |
| --- | --- |
| Install and run my first Task | [Quick start](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart) |
| Submit and inspect tasks in a browser | [Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio) |
| Run the research chain and understand results | [Research workflow](https://flowllm-ai.github.io/AxonX/en/research/workflow) |
| Configure the research assistant or external MCP tools | [Agent configuration](https://flowllm-ai.github.io/AxonX/en/agent/configuration) · [MCP integration](https://flowllm-ai.github.io/AxonX/en/agent/mcp-integration) |
| Execute on another machine | [Remote machines](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines) |
| Configure and call AxonX | [Configuration](https://flowllm-ai.github.io/AxonX/en/reference/configuration) · [CLI](https://flowllm-ai.github.io/AxonX/en/reference/cli) · [Python](https://flowllm-ai.github.io/AxonX/en/reference/python) |
| Build research tasks or framework extensions | [Development guide](https://flowllm-ai.github.io/AxonX/en/dev_guide) · [Framework extensions](https://flowllm-ai.github.io/AxonX/en/development/framework-extensions) |

Browse the [complete documentation](https://flowllm-ai.github.io/AxonX/en/docs). Bilingual source documents live in [docs/](docs/README.md).

## Contributing

Bug reports, feature requests, documentation improvements, research plugins, and code contributions are welcome. Search [existing issues](https://github.com/FlowLLM-AI/AxonX/issues) and read the [contribution guide](CONTRIBUTING.md) for development setup and checks.

## License

AxonX is released under the [Apache License 2.0](LICENSE).
