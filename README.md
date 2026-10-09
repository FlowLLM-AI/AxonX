<p align="center">
  <img src="https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/axonx_studio/public/axonx-logo.svg" alt="AxonX" width="560" />
</p>

<p align="center"><strong>An Agent Harness for financial quantitative research.</strong></p>

<p align="center">
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&amp;logoColor=white&amp;style=flat-square" alt="Python 3.12+" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/v/axonx?logo=pypi&amp;logoColor=white&amp;style=flat-square" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/dm/axonx?label=downloads%2Fmonth&amp;style=flat-square&amp;logo=pypi&amp;logoColor=white" alt="PyPI monthly downloads" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/m/FlowLLM-AI/AxonX?label=commits%2Fmonth&amp;style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub monthly commit activity" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/graphs/traffic"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fflowllm-ai.github.io%2FAxonX%2Fbadges%2Fclones.json&amp;style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub clones in the last 14 days" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/forks"><img src="https://img.shields.io/github/forks/FlowLLM-AI/AxonX?label=forks&amp;style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub forks" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square&amp;logo=apache&amp;logoColor=white" alt="Apache License 2.0" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/en/concepts/architecture"><img src="https://img.shields.io/badge/access-CLI%20%2F%20MCP-6366f1?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMyA0aDE4djE2SDN6IE03IDhsNCA0LTQgNCBNMTMgMTZoNCIvPjwvc3ZnPg%3D%3D&amp;logoColor=white" alt="CLI and MCP access" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/en/docs"><img src="https://img.shields.io/badge/docs-AxonX-blue?style=flat-square&amp;logo=readthedocs&amp;logoColor=white" alt="AxonX documentation" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/README.md"><img src="https://img.shields.io/badge/English-Read-yellow?style=flat-square&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/README_ZH.md"><img src="https://img.shields.io/badge/%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-%E9%98%85%E8%AF%BB-orange?style=flat-square&amp;logo=googletranslate&amp;logoColor=white" alt="阅读简体中文" /></a>
  <a href="https://deepwiki.com/FlowLLM-AI/AxonX"><img src="https://img.shields.io/badge/DeepWiki-Ask_Devin-navy?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMyA0aDZsMyAyIDMtMmg2djE2aC02bC0zIDItMy0ySDN6IE0xMiA2djE2Ii8%2BPC9zdmc%2B&amp;logoColor=white" alt="Ask DeepWiki about AxonX" /></a>
</p>

<p align="center">⭐ <a href="https://github.com/FlowLLM-AI/AxonX">Give AxonX a Star on GitHub</a>!</p>

<a id="what-is-axonx"></a>

## 🧠 What is AxonX?

**AxonX is an agent-native harness for financial quantitative research.**

It packages data processing, factor analysis, training, prediction, and backtesting as **Tasks** with
explicit inputs and outputs. Plugins provide the algorithms; the framework handles execution, records, and artifact
management.

Researchers use forms and charts in **AxonX Studio**, while Agents and scripts access capabilities through CLI / MCP.
Each interface submits, tracks, and queries tasks through **Jobs**, using research records in the same workspace to
inspect logs, artifacts, and upstream and downstream relationships.

<a id="why-axonx"></a>

## ✨ Why AxonX?

- Reusable research Tasks. Typed inputs and outputs define data, model, and artifact requirements. → [Task contracts](https://flowllm-ai.github.io/AxonX/en/reference/task-contracts)
- Manage execution. Run Tasks in worker processes; track status, progress, logs, and results; wait or cancel. → [Task management](https://flowllm-ai.github.io/AxonX/en/guides/task-management)
- Trace research results. Saved parameters, artifacts, and dependency graphs help you reuse data and compare experiments. → [Task lineage](https://flowllm-ai.github.io/AxonX/en/concepts/task-lineage)
- One workflow across interfaces. CLI / MCP, Studio, and Agents share Job and Task contracts, records, and artifacts. → [AxonX Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio) · [Agent](https://flowllm-ai.github.io/AxonX/en/agent/usage)
- Extend and run remotely. Add research plugins and execute Tasks in a selected target environment. → [Plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management) · [Remote machines](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines)

## 📰 Latest Updates

- AxonX **0.1.0** released: an agent-native quantitative research harness with plugin-based Tasks, execution tracking, task lineage, and shared CLI / MCP / Studio access. → [Documentation](https://flowllm-ai.github.io/AxonX/en/)
- Connect your Agent with SKILL.md + CLI: load the [AxonX Skill](skills/axonx/SKILL.md) into Codex, Claude Code, or another Agent to discover Task contracts, develop plugins, submit research tasks, and inspect results. → [Agent integration](https://flowllm-ai.github.io/AxonX/en/agent/external)
- AxonX Studio available: browse tasks and artifacts, inspect training curves and backtests, and compare strategies in one workspace. → <a href="https://flowllm-ai.github.io/AxonX/playground/?lang=en" target="_self">Try Playground</a> (simulated data and execution)
- Qlib three-layer experiment: shared data and 0.05% buy / 0.15% sell fees; policy-layer Top20/Top30 net annualized returns are **19.35%/15.72%**. Factor groups use training validation, the primary policy is fixed in advance, and results include missing quotes. → [Complete record](plugins/qlib_a158/THREE_LAYER_EXPERIMENTS.md)

![AxonX research and execution overview](docs/figures/getting-started/overview.svg?v=20261004-flat)

<a id="quick-start"></a>

## 🚀 Quick start

Requires **Python 3.12+**. Local Task execution supports **macOS and Linux**.

### Install from PyPI

```bash
pip install "axonx[studio]"
```

Includes the CLI, HTTP API, MCP, and prebuilt AxonX Studio. For core capabilities alone, install `axonx`. Research
plugins are installed separately.

### Install from source

Building Studio requires Node.js 22.13+ (22.x), 24.x, or 26+:

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git && cd AxonX
pip install -e .
(cd axonx_studio && npm ci && npm run build)
pip install ./axonx_studio
```

For development dependencies and frontend hot reload, see the [contribution guide](CONTRIBUTING.md)
and [Studio development documentation](https://flowllm-ai.github.io/AxonX/en/development/studio).

### Configure environment variables

Create `.env` in the startup directory. The CLI automatically loads configuration from the current directory or a parent
directory; existing environment variables take precedence.

```dotenv
# Local service authentication: replace with your own token
AXONX_SERVICE_TOKEN=replace-with-your-local-service-token

# Optional: target AxonX service (axonx start --config remote)
# AXONX_TARGET=192.0.2.10:1024
# AXONX_TARGET_TOKEN=your-target-service-token
```

For optional settings such as models, market-data downloads, and remote services, see [example.env](example.env).

### Start AxonX

Start with the defaults:

```bash
axonx start
```

Specify the listening IP and port:

```bash
axonx start --service.host 127.0.0.1 --service.port 8181
```

With a custom port, open `http://127.0.0.1:8181/` in your browser. Append `--target 127.0.0.1:8181` to subsequent CLI
service commands and provide the local service token, for example:

```bash
axonx version --target 127.0.0.1:8181 --token '<local-service-token>'
```

When `--target` is specified, the CLI reads `AXONX_TARGET_TOKEN` by default; the `--token` above explicitly supplies
local credentials. Local commands using the default port read `AXONX_SERVICE_TOKEN`. For remote service configuration,
see [remote execution](#connect-directly-to-a-remote-service-with-the-cli).

Keep the service running and execute subsequent CLI commands in another terminal.

### Open AxonX Studio

After starting with the defaults, open `http://127.0.0.1:1024/`, go to **Settings → Local service token**, and enter the
`AXONX_SERVICE_TOKEN` configured in `.env`. You can then:

- Query Task definitions, fill in parameters, submit tasks, and inspect status, progress, logs, and upstream and
  downstream relationships.
- Browse workspace files and inspect parameters, metadata, and research artifacts.
- View factor analysis, training curves, predictions, backtest metrics, and period summaries.
- Query machine resources and switch between configured local and remote services.
- After configuring a model, use conversations on the Agent page to investigate tasks and analyze research results.

<table>
  <tr>
    <th width="50%">Home</th>
    <th width="50%">Task management</th>
  </tr>
  <tr>
    <td valign="top">
      <a href="docs/figures/studio/home.png"><img src="docs/figures/studio/home.png" alt="AxonX Studio home" width="100%" /></a>
    </td>
    <td valign="top">
      <a href="docs/figures/studio/task-list.png"><img src="docs/figures/studio/task-list.png" alt="AxonX Studio task management: task status, progress, and feature navigation" width="100%" /></a>
    </td>
  </tr>
</table>

[Getting started with Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio)

<a id="quick-demo"></a>

## 🧪 Quick CLI demo

### Download Tushare data

Set `AXONX_TUSHARE_TOKEN` in the service's `.env` ([example.env](example.env)), then start or restart the service.
Download a week's daily prices and adjustment factors with the built-in Tushare Task, then check its status and logs:

```bash
axonx submit \
  --task download_tushare_task \
  --task-name tushare-demo \
  --start-date 20230901 \
  --end-date 20230907 \
  --datasets 'daily,adj_factor'

axonx status --task-id 'api#download_tushare_task#tushare-demo'
axonx read_task_log --task-id 'api#download_tushare_task#tushare-demo'
```

`--task` selects the Task and `--task-name` names it. Dates use `YYYYMMDD`; `--datasets` selects comma-separated data
groups. The `submit` command returns JSON (mock response):

```json
{
  "answer": {
    "task_id": "api#download_tushare_task#tushare-demo",
    "run_id": "f5caee3a7b3c40849d0fb3bdc0f0cd23",
    "task": "download_tushare_task"
  },
  "success": true,
  "metadata": {}
}
```

`success: true` confirms submission; the Task downloads asynchronously and saves Parquet files under the workspace's
`tushare/` directory when it succeeds.
Use the returned `task_id` for queries and save `run_id` to wait for this execution with `wait_task`.

### Other CLI commands

Replace placeholder IDs with the returned `answer.task_id` / `answer.run_id`; submit downstream Tasks only after their
inputs succeed.

```bash
# Task status, logs, and dependencies
axonx wait_task --task-id '<task_id>' --run-id '<run_id>' --client-timeout 600
axonx status --task-id '<task_id>'
axonx read_task_log --task-id '<task_id>'
axonx get_task_graph --task-id '<task_id>'

# Service and workspace
axonx version
axonx machine_status
axonx list_entries --path ''

# Plugins: install in the service's Python environment, then restart the service
pip install axonx-qlib-a158
axonx plugin list
axonx plugin show axonx-qlib-a158

# Research workflow (skip downloads if historical data is already available)
axonx get_task_definition --task qlib_a158_etl
axonx submit --task download_tushare_task --start-date 20140101 --end-date 20231231 --datasets 'static,stk_limit,daily,adj_factor,index_weight'
axonx submit --task qlib_a158_etl --start-date 20150101 --end-date 20231231
axonx submit --task qlib_a158_train --source-tasks '<etl_task_id>' --train-start 20150101 --train-end 20230101
axonx submit --task qlib_a158_predict --source-tasks '<train_task_id>' --pred-start 20230101 --pred-end 20231231
axonx submit --task qlib_a158_backtest --source-tasks '<predict_task_id>'
# Optional factor analysis: an independent downstream stage of ETL
axonx submit --task qlib_a158_factor --source-tasks '<etl_task_id>'
```

View results in **AxonX Studio**; see the [research workflow](https://flowllm-ai.github.io/AxonX/en/research/workflow) and
[CLI reference](docs/en/reference/cli.md) for details.

<a id="agent-access-and-development-guides"></a>

## 🤝 Agent access and development guides

| Method         | Usage                                                                                                                                  | Development guide                                                                                                                                              |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Built-in Agent | Configure a model, then use **Studio → Agent**; see [example.env](example.env) for model settings.                                     | Optionally load the development guide bundled with the installation. Its language follows the application's `language` setting, which defaults to English.     |
| External Agent | Configure the [AxonX Skill](skills/axonx/SKILL.md) for Codex, Claude Code, or another Agent, and access the service through CLI / MCP. | Keep the source checkout referenced by the Skill, or adjust its documentation paths; see the [English development and operations guide](docs/en/dev_guide.md). |

### Connect an external Agent through MCP

After starting the service with the defaults, use these connection parameters in your Agent host:

| Parameter             | Value                                         |
| --------------------- | --------------------------------------------- |
| URL                   | `http://127.0.0.1:1024/mcp`                   |
| Transport             | Streamable HTTP                               |
| Authentication header | `Authorization: Bearer <AxonX service token>` |

Use the `AXONX_SERVICE_TOKEN` of the service you connect to; adjust the host and port for a custom or remote service.
For host configuration and tool discovery, see [MCP integration](https://flowllm-ai.github.io/AxonX/en/agent/mcp-integration).

### Configure the built-in Agent

The default backend uses the **Claude Agent SDK**. Set the model credentials, compatible service URL, and model name in
`.env`:

```dotenv
CLAUDE_CODE_API_KEY=your-model-api-key
CLAUDE_CODE_BASE_URL=https://api.anthropic.com
CLAUDE_CODE_MODEL_NAME=your-model-name
```

Replace the placeholders with your provider's credentials and available model name, and use its Claude-compatible URL.
Restart AxonX after changing `.env`; then open **Studio → Agent**. See [example.env](example.env) for other optional settings.

The built-in Agent's `components.agent.default.load_dev_guide` defaults to `false`. To load the Chinese guide, override
the configuration in the startup command:

```bash
axonx start --components.agent.default.load_dev_guide true --language zh
```

Guide loading and tool configuration are independent. The Jobs available to the Agent are determined by `job_tools`,
which provides task and artifact queries by default.
See [Agent configuration](https://flowllm-ai.github.io/AxonX/en/agent/configuration).

<a id="alpha158-and-the-plugin-system"></a>

## 🧩 Alpha158 and the plugin system

[Alpha158](plugins/qlib_a158/README.md) packages 158 price and volume features, a LightGBM model, and TopN backtesting as
research Tasks. The main chain is **ETL → Train → Predict → Backtest**, with factor analysis as an independent
downstream stage of ETL.

| Stage           | Main artifacts                                             |
| --------------- | ---------------------------------------------------------- |
| Data processing | Features, labels, trading status, and statistics.          |
| Factor analysis | Factor diagnostics; not a prerequisite for training.       |
| Training        | LightGBM model, validation curves, and feature importance. |
| Prediction      | Out-of-sample predictions and statistics.                  |
| Backtesting     | TopN backtests, period summaries, and holdings artifacts.  |

For usage examples, see the [Quick CLI demo](#quick-demo) above; for complete parameters and data requirements, see
the [plugin documentation](plugins/qlib_a158/README.md). To extend your own research methods, inspect, build, and install
plugins from source. Relevant commands appear under [CLI commands](#axonx-cli-commands-and-remote-execution) below; for
development and deployment, see [plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management).

<a id="benchmark-agent-developed-market-cross-sectional-features"></a>

## 📊 Benchmark: Agent-developed market cross-sectional features

Research uses `qlib_a158 → qlib_factor → qlib_strategy` for base features, context factors and portfolio policies. Submit and record experiments through the [AxonX Skill](skills/axonx/SKILL.md) and [development guide](docs/en/dev_guide.md).

Use rank × AxonX parameters, train on `[20150101,20230101)`, and evaluate `20230103–20261008`. Fees: 0.05% buy / 0.15% sell. Training-period validation RankIC selects `liquidity` (164 features) from 16 factor candidates. The primary policy is fixed at a 10-day minimum and a 20% daily count cap per side; 12 holding-period comparisons use base and factor predictions.

| Layer         | Top20 net annualized | Top30 net annualized |
| ------------- | -------------------: | -------------------: |
| qlib_a158     |                7.67% |                0.97% |
| qlib_factor   |               -1.83% |               -1.58% |
| qlib_strategy |               19.35% |               15.72% |

Shared data match value by value; the complete no-context prediction reproduces the base. Missing quotes produce `incomplete_market_data`; 2026 ends on October 8.

![Qlib three-layer net annualized returns](docs/figures/benchmark/qlib-topn-results.svg)

[Complete three-layer record](plugins/qlib_a158/THREE_LAYER_EXPERIMENTS.md) · [Base scheme](plugins/qlib_a158/README.md) · [All factor candidates](plugins/qlib_factor/EXPERIMENT_RESULTS.md) · [All policy candidates](plugins/qlib_strategy/EXPERIMENT_RESULTS.md).

## 🛠️ AxonX CLI commands and remote execution

CLI service commands call the corresponding Jobs. `exec` and plugin management commands without a specified target run
in the current Python environment.

| Purpose                               | Example commands                                                                              |
| ------------------------------------- | --------------------------------------------------------------------------------------------- |
| Help / service version                | `axonx help` / `axonx version`                                                                |
| Start the service                     | `axonx start`                                                                                 |
| List registered Tasks                 | `axonx exec` / `axonx list_installed_task_definitions`                                        |
| Query a Task contract                 | `axonx get_task_definition --task qlib_a158_etl`                                              |
| Execute in the current process        | `axonx exec --task demo --x 2 --y 3`                                                          |
| Submit a research task                | `axonx submit --task qlib_a158_train --source-tasks '<etl_task_id>'`                          |
| Wait for this run                     | `axonx wait_task --task-id '<task_id>' --run-id '<run_id>' --client-timeout 86400`            |
| Follow progress and logs              | `axonx stream_task --task-id '<task_id>' --stream true`                                       |
| Query task list / status              | `axonx list_task_statuses` / `axonx status --task-id '<task_id>'`                             |
| Read logs                             | `axonx read_task_log --task-id '<task_id>'`                                                   |
| Query context / dependency graph      | `axonx get_task_context --task-id '<task_id>'` / `axonx get_task_graph --task-id '<task_id>'` |
| Cancel a task                         | `axonx cancel --task-id '<task_id>'` / `axonx cancel --run-id '<run_id>'`                     |
| Delete finished tasks and their files | `axonx delete_tasks --task-ids '["<task_id>"]'`                                               |
| Browse the workspace                  | `axonx list_entries --path ''`                                                                |
| Preview an artifact                   | `axonx preview_file --path '<workspace-relative-path>'`                                       |
| Query machines / resources            | `axonx list_machines` / `axonx machine_status`                                                |
| Query plugins / details               | `axonx plugin list` / `axonx plugin show axonx-qlib-a158`                                     |
| Inspect / build plugin source         | `axonx plugin inspect ./plugins/qlib_a158` / `axonx plugin build ./plugins/qlib_a158`         |
| Install / uninstall a plugin          | `axonx plugin install ./plugins/qlib_a158` / `axonx plugin uninstall axonx-qlib-a158`         |

### Connect directly to a remote service with the CLI

First install AxonX and research plugins on the target machine, configure its own `AXONX_SERVICE_TOKEN`, and start a
reachable service. On the client, configure the target token and explicitly specify the address for commands that
support remote access:

```bash
export AXONX_TARGET_TOKEN='your-target-service-token'
axonx machine_status --target 192.0.2.10:1024
axonx plugin list --target 192.0.2.10:1024
axonx submit --task demo --x 2 --y 3 --target 192.0.2.10:1024
axonx wait_task --task-id '<task_id>' --run-id '<run_id>' \
  --client-timeout 120 --target 192.0.2.10:1024
```

Replace the example address with your actual service. Use the same `--target` for submission, waiting, status, logs, and
artifact queries; tasks use the target machine's plugins, data, and workspace. Direct CLI access does not require
starting a local service.

Remote plugin installation builds a wheel locally, uploads it, and installs it in the target environment:

```bash
axonx plugin install ./plugins/qlib_a158 --target 192.0.2.10:1024
```

`plugin build` always runs locally. Remote `plugin inspect` accepts a distribution or plugin name already installed on
the target. `start` and `exec` do not execute remotely through `--target`.

### Use remote machines in Studio

Configure the remote service address and token in the local `.env`:

```dotenv
# Optional: remote AxonX service for Studio
AXONX_TARGET=192.0.2.10:1024
AXONX_TARGET_TOKEN=your-target-service-token
```

Replace the example address with your actual service, then start with the built-in `remote` configuration:

```bash
axonx start --config remote
```

`remote` inherits the default configuration and adds the target address and token to the service's `targets`. Studio
uses the local token to access the same-origin backend, which forwards requests to the selected remote service. For
multiple targets, custom YAML, and connection troubleshooting, see
the [remote machines guide](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines).

<a id="axonx-documentation"></a>

## 📚 AxonX documentation

| Topic                             | GitHub Pages documentation                                                                                                                                                                                                                                                                                                          |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Installation and your first Task  | [Quick start](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart)                                                                                                                                                                                                                                                     |
| Browser operation                 | [AxonX Studio](https://flowllm-ai.github.io/AxonX/en/getting-started/studio)                                                                                                                                                                                                                                                        |
| Component, Job, Task              | [Architecture](https://flowllm-ai.github.io/AxonX/en/concepts/architecture) · [Framework extensions](https://flowllm-ai.github.io/AxonX/en/development/framework-extensions)                                                                                                                                                        |
| Task contracts and lifecycle      | [Task contracts](https://flowllm-ai.github.io/AxonX/en/reference/task-contracts) · [Task management](https://flowllm-ai.github.io/AxonX/en/guides/task-management) · [Task lineage](https://flowllm-ai.github.io/AxonX/en/concepts/task-lineage)                                                                                    |
| Agent development and operations  | [External agents](https://flowllm-ai.github.io/AxonX/en/agent/external) · [Development guide](https://flowllm-ai.github.io/AxonX/en/dev_guide) · [Agent configuration](https://flowllm-ai.github.io/AxonX/en/agent/configuration) · [MCP integration](https://flowllm-ai.github.io/AxonX/en/agent/mcp-integration)                  |
| Plugin development and deployment | [Plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management) · [Alpha158](https://flowllm-ai.github.io/AxonX/en/plugins/qlib-a158) · [Qlib Factor](https://flowllm-ai.github.io/AxonX/en/plugins/qlib-factor)                                                                                                      |
| Quantitative research             | [Research workflow](https://flowllm-ai.github.io/AxonX/en/research/workflow) · [Experiment design](https://flowllm-ai.github.io/AxonX/en/research/experiments) · [Interpreting results](https://flowllm-ai.github.io/AxonX/en/research/results) · [Interpreting backtests](https://flowllm-ai.github.io/AxonX/en/research/backtest) |
| Remote execution                  | [Remote machines](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines)                                                                                                                                                                                                                                                     |
| CLI and configuration             | [CLI](https://flowllm-ai.github.io/AxonX/en/reference/cli) · [Configuration](https://flowllm-ai.github.io/AxonX/en/reference/configuration)                                                                                                                                                                                         |

Browse the [complete Chinese documentation](https://flowllm-ai.github.io/AxonX/zh/docs)
or [English documentation](https://flowllm-ai.github.io/AxonX/en/docs).

<a id="contributing"></a>

## 💬 Contributing

Bug reports, feature requests, documentation improvements, research plugins, and code contributions are welcome.
Search [existing issues](https://github.com/FlowLLM-AI/AxonX/issues) first; see
the [contribution guide](CONTRIBUTING.md) for development setup, directory conventions, and required checks.

Keep research algorithms in `plugins/` and reuse framework extension points. Update both English and Chinese
documentation when behavior changes. When contributing experiments, include data and time windows, parameters, cost
definitions, and result materials that others can verify.

<a id="license"></a>

## ⚖️ License

AxonX is released under the [Apache License 2.0](LICENSE).
