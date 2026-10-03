<p align="center">
  <img src="axonx_studio/public/axonx-logo.svg" alt="AxonX" width="560" />
</p>

<p align="center"><strong>An agent-native harness for quantitative research.</strong></p>

<p align="center">
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&amp;logoColor=white&amp;style=flat-square" alt="Python 3.12+" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/v/axonx?logo=pypi&amp;logoColor=white&amp;style=flat-square" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/dm/axonx?label=downloads%2Fmonth&amp;style=flat-square" alt="PyPI monthly downloads" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/m/FlowLLM-AI/AxonX?label=commits%2Fmonth&amp;style=flat-square" alt="GitHub monthly commit activity" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square" alt="Apache License 2.0" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/en/concepts/architecture"><img src="https://img.shields.io/badge/access-CLI%20%2F%20MCP-6366f1?style=flat-square" alt="CLI and MCP access" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/en/plugins/management"><img src="https://img.shields.io/badge/plugins-extensible-0d9488?style=flat-square" alt="Extensible plugins" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/en/guides/remote-machines"><img src="https://img.shields.io/badge/execution-multi--machine-0284c7?style=flat-square" alt="Multi-machine execution" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/en/docs"><img src="https://img.shields.io/badge/docs-AxonX-blue?style=flat-square" alt="AxonX documentation" /></a>
  <a href="README.md"><img src="https://img.shields.io/badge/English-Read-yellow?style=flat-square" alt="Read in English" /></a>
  <a href="README_ZH.md"><img src="https://img.shields.io/badge/%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-%E9%98%85%E8%AF%BB-orange?style=flat-square" alt="阅读简体中文" /></a>
  <a href="https://deepwiki.com/FlowLLM-AI/AxonX"><img src="https://img.shields.io/badge/DeepWiki-Ask_Devin-navy?style=flat-square" alt="Ask DeepWiki about AxonX" /></a>
</p>

## What is AxonX?

AxonX connects research code, task execution, logs, and results in one workspace. It represents data processing, factor analysis, training, prediction, and backtesting as Tasks with explicit input and output contracts. CLI, AxonX Studio, and Agent access the same capabilities through Job interfaces.

Researchers can inspect how a result was produced, reuse upstream data, compare experiments, and let an Agent investigate tasks and artifacts. Plugin authors supply the research algorithms; AxonX provides the execution and inspection infrastructure. AxonX is currently in alpha.

## Why AxonX?

- **Reuse research code as Tasks.** Typed inputs and outputs make data, model, and artifact requirements explicit. → [Task contracts](https://flowllm-ai.github.io/AxonX/en/reference/task-contracts)
- **Execution you can inspect.** Submit Tasks to independent worker processes and follow status, progress, logs, and results. → [Task management](https://flowllm-ai.github.io/AxonX/en/guides/task-management)
- **Trace results back to their inputs.** Workspace records keep parameters, artifacts, and upstream Task IDs together so you can reuse datasets and inspect experiment differences. → [Task lineage](https://flowllm-ai.github.io/AxonX/en/concepts/task-lineage)
- **One workflow across CLI, AxonX Studio, and Agent.** Use scripts, browser forms and charts, or an assistant that reads task evidence through configured tools. → [AxonX Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio) · [Agent](https://flowllm-ai.github.io/AxonX/en/agent/usage)
- **Extend and run remotely.** Package research capabilities as plugins and explicitly choose a remote execution target. → [Plugins](https://flowllm-ai.github.io/AxonX/en/plugins/management) · [Remote machines](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines)

## AxonX Studio

AxonX Studio provides task submission, run details, machine resources, workspace browsing, and research result views.

![AxonX Studio home](docs/figures/studio/home.png)

See [Getting started with AxonX Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio) for setup and connection instructions.

## Quick start

Requires **Python 3.12+**, with local Task execution on **macOS and Linux**. Use an activated virtual environment.

### Install from PyPI

```bash
pip install "axonx[studio]"
```

This includes the CLI, API, MCP, and prebuilt AxonX Studio. For the core alone, install `axonx`.

### Install from source

Requires Node.js 22.13+ (22.x), 24.x, or 26+ to build AxonX Studio:

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e .
cd axonx_studio
npm ci && npm run build
cd ..
pip install ./axonx_studio
```

This installs the core from source and builds and installs AxonX Studio locally. See [Contributing](https://flowllm-ai.github.io/AxonX/en/development/contributing) for development setup and [AxonX Studio development](https://flowllm-ai.github.io/AxonX/en/development/studio) to modify the frontend.

### Configure .env

Create `.env` in the directory where you start AxonX. The CLI loads it automatically; existing environment variables take precedence.

```dotenv
# Service authentication: choose your own token
AXONX_SERVICE_TOKEN=replace-with-your-local-service-token

# Optional: built-in Agent (Claude-compatible backend)
# CLAUDE_CODE_API_KEY=your-api-key
# CLAUDE_CODE_BASE_URL=https://api.anthropic.com
# CLAUDE_CODE_MODEL_NAME=your-model-name

# Optional: Tushare data download
# AXONX_TUSHARE_TOKEN=your-tushare-token
# AXONX_TUSHARE_BASE_URL=http://api.waditu.com/dataapi
```

The service token is sufficient for task management and AxonX Studio. Fill in the Agent settings when using the research assistant, or the Tushare token when downloading market data; override the Tushare URL only for a compatible custom endpoint. See [example.env](example.env) for remote-service and DingTalk settings. Keep `.env` out of version control.

### Open AxonX Studio

```bash
axonx start --service.host 127.0.0.1
```

Open <http://127.0.0.1:1024/> and enter `AXONX_SERVICE_TOKEN` from `.env` in **Settings → Service token**. See the [full quick start](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart) for asynchronous submission, waiting, and result inspection.

## Research with an Agent

The built-in assistant uses the Claude Agent SDK and configured Job tools to inspect task status, logs, upstream relationships, and workspace artifacts. Configure the [Agent backend](https://flowllm-ai.github.io/AxonX/en/agent/configuration), then open **Agent** in AxonX Studio. Ordinary research Tasks can run without model credentials.

Give it specific Task IDs and questions, for example:

- “Check Task `<task_id>`'s status, tail logs, and upstream tasks. Explain where it failed and what to inspect next.”
- “Compare Backtest Tasks `<A>` and `<B>`: check their common date window and cost assumptions before explaining the results.”

External Agents can also connect to the service's Streamable HTTP MCP endpoint at `http://127.0.0.1:1024/mcp` using the service's Bearer token. Available tools depend on the service configuration. See [Agent usage](https://flowllm-ai.github.io/AxonX/en/agent/usage) and [MCP integration](https://flowllm-ai.github.io/AxonX/en/agent/mcp-integration) for tools and permissions.

### Repository skill

The repository includes an [AxonX skill](skills/axonx/SKILL.md) for Agents working with research plugins, Task execution, logs, and artifacts. It references the maintained [development and operations guide](docs/en/dev_guide.md).

In an Agent session with access to this checkout, ask: “Read `skills/axonx/SKILL.md` and use it to inspect Task `<task_id>`.” Automatic discovery depends on the Agent's skill configuration; adding this directory does not automatically load it into AxonX Studio's built-in assistant. Keep the source checkout available because the skill references repository documents.

## How it works

**CLI / AxonX Studio / external Agent → Job interfaces → Task execution → workspace records and artifacts.**

Jobs validate calls and coordinate framework capabilities. For research submission, the TaskManager starts a worker process and returns a run identifier; the Task writes status, logs, and outputs. Query Jobs and AxonX Studio then read those records. `axonx exec` runs a Task directly in the current process.

Research plugins supply the algorithms. Upstream Task IDs record relationships, while users or scripts organize stage-by-stage execution. See the [architecture](https://flowllm-ai.github.io/AxonX/en/concepts/architecture) for the component boundaries.

## Quantitative research and plugins

![AxonX research and execution overview](docs/figures/getting-started/overview.svg)

A typical research chain is **raw data → ETL → training → prediction → backtesting**, with factor analysis branching from ETL. Tasks record upstream IDs through `source_tasks`, so datasets and predictions can be reused across experiments. Users or calling programs submit each stage.

The core supplies Task contracts and runtime infrastructure. Research plugins implement factors, models, and backtesting logic:

| Plugin source                                                                        | Purpose                                                  |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------- |
| [Alpha158](https://flowllm-ai.github.io/AxonX/en/plugins/alpha158)                   | Alpha158 research task implementations                   |
| [Alpha158 Enhanced](https://flowllm-ai.github.io/AxonX/en/plugins/alpha158-enhanced) | Extended Alpha158 research tasks and experiment guidance |

Install a research plugin in the execution service's Python environment, then restart the service:

```bash
pip install axonx-alpha158
# Or: pip install axonx-alpha158-enhanced
```

Start with the [research workflow](https://flowllm-ai.github.io/AxonX/en/research/workflow) for plugin installation and data prerequisites. Market-data and Agent features need their own provider configuration. See [Interpreting backtests](https://flowllm-ai.github.io/AxonX/en/research/backtest) for return definitions, costs, and trading assumptions.

AxonX Studio reads the resulting artifacts to display training metrics, predictions, and backtest summaries. For example, the backtest view shows overall signal metrics alongside period summaries:

![AxonX Studio backtest overall metrics](docs/figures/studio/backtest-overall.png)

This screenshot illustrates an existing experiment's result view. See [Research results](https://flowllm-ai.github.io/AxonX/en/research/results) for how to read each stage's outputs.

## Documentation

| I want to…                                             | Guide                                                                                                                                                                                                          |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Install and run my first Task                          | [Quick start](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart)                                                                                                                                |
| Submit and inspect tasks in a browser                  | [AxonX Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio)                                                                                                                                   |
| Run the research chain and understand results          | [Research workflow](https://flowllm-ai.github.io/AxonX/en/research/workflow)                                                                                                                                   |
| Configure the research assistant or external MCP tools | [Agent configuration](https://flowllm-ai.github.io/AxonX/en/agent/configuration) · [MCP integration](https://flowllm-ai.github.io/AxonX/en/agent/mcp-integration)                                              |
| Execute on another machine                             | [Remote machines](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines)                                                                                                                                |
| Configure and call AxonX                               | [Configuration](https://flowllm-ai.github.io/AxonX/en/reference/configuration) · [CLI](https://flowllm-ai.github.io/AxonX/en/reference/cli) · [Python](https://flowllm-ai.github.io/AxonX/en/reference/python) |
| Build research tasks or framework extensions           | [Development guide](https://flowllm-ai.github.io/AxonX/en/dev_guide) · [Framework extensions](https://flowllm-ai.github.io/AxonX/en/development/framework-extensions)                                          |

Browse the [complete bilingual documentation](https://flowllm-ai.github.io/AxonX/en/docs).

## Contributing

Bug reports, feature requests, documentation improvements, research plugins, and code contributions are welcome. Search [existing issues](https://github.com/FlowLLM-AI/AxonX/issues) and read the [contribution guide](https://flowllm-ai.github.io/AxonX/en/development/contributing) for development setup and checks.

## License

AxonX is released under the [Apache License 2.0](LICENSE).
