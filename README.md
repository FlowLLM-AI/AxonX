<p align="center">
  <img src="https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/axonx_studio/public/axonx-logo.svg" alt="AxonX" width="560" />
</p>

<p align="center"><strong>Turn research prompts into quantitative code and traceable experiments.</strong></p>

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

**AxonX is an agent-native harness for quantitative research, providing unified tools and a runtime for quantitative code development, experiment execution, and result analysis.**

Combine your exploration prompt with the [AxonX Skill](skills/axonx/SKILL.md), and use an external or built-in Agent
to develop a new research plugin or optimize an existing one. The Agent writes quantitative code, runs experiments
through AxonX, inspects results, and iterates on factors, models, and portfolio strategies.
**You define the research question; the Agent implements it; the Harness manages execution and evidence.**

The reference workflow starts from **Qlib's Alpha158 / LightGBM**, then extends it through
**`qlib_a158` → `qlib_factor` → `qlib_strategy`**. AxonX ports and adapts the Qlib workflow into typed Tasks and
provides the development and execution environment for exploring improvements. The same plugin contracts can host
other quantitative research methods.

CLI, HTTP, MCP, and **AxonX Studio** share Jobs for submitting and querying Tasks. The selected execution service
runs plugin code and stores parameters, status, dependencies, and artifacts in its workspace, so researchers and
Agents can inspect the same evidence.

[Agent development](#agent-access-and-development-guides) · [Plugins](#alpha158-and-the-plugin-system) ·
[Experiments](#benchmark-agent-developed-market-cross-sectional-features) · [Quick start](#quick-start) ·
<a href="https://flowllm-ai.github.io/AxonX/playground/?lang=en" target="_self">Try Playground</a>

<a id="why-axonx"></a>

## ✨ Why AxonX?

- **Turn research questions into quantitative code.** The Skill teaches plugin authoring, Task contracts, execution, and evidence inspection; your prompt defines what the Agent explores. → [AxonX Skill](skills/axonx/SKILL.md)
- **Extend a working baseline.** Add features, change training logic, or develop portfolio policies in plugins while reusing compatible implementations and artifacts. → [Alpha158](plugins/qlib_a158/README.md) · [Factor](plugins/qlib_factor/README.md) · [Strategy](plugins/qlib_strategy/README.md)
- **Execute experiments with consistent contracts.** Discover typed inputs and outputs, submit worker-process Tasks, follow progress and logs, wait for completion, or cancel a run. → [Task management](https://flowllm-ai.github.io/AxonX/en/guides/task-management)
- **Connect code changes to evidence.** Inspect configurations, Task/Run IDs, dependencies, models, predictions, and backtest artifacts to investigate failures and compare candidates. → [Task lineage](https://flowllm-ai.github.io/AxonX/en/concepts/task-lineage) · [Experiment design](docs/en/research/experiments.md)
- **Use your preferred Agent and execution target.** Work through an external Agent or Studio's built-in Agent, inspect results visually, and run Tasks on a selected local or remote service. → [Agent integration](https://flowllm-ai.github.io/AxonX/en/agent/external) · [Remote machines](https://flowllm-ai.github.io/AxonX/en/guides/remote-machines)

## 📰 Latest Updates

- **Alpha158 enhancement experiments:** adapted baseline / risk-factor model / 3-day rank-retention strategy report Top20 net annualized returns of **7.67% / 9.03% / 32.37%**. Runs use 0.05% buy / 0.15% sell fees, report incomplete market data, and have no independent confirmation window. → [Full results and provenance](docs/en/research/experiments.md#comparison)
- **Research plugin stack:** Alpha158, selectable factor groups, and rank-retention policies share research contracts and backtest accounting. Current source versions: AxonX **0.1.1**, research plugins **0.2.0**. → [Plugin system](#alpha158-and-the-plugin-system)
- **Agent and Studio workflow:** develop with Skill + prompt; inspect Tasks, factors, training curves, predictions, and strategy comparisons in Studio. → <a href="https://flowllm-ai.github.io/AxonX/playground/?lang=en" target="_self">Try Playground</a> (simulated data and execution)

![AxonX research and execution overview](docs/figures/getting-started/overview.svg?v=20261010-agent-code)

<a id="agent-access-and-development-guides"></a>

## 🤝 Develop quantitative plugins with an Agent

The development loop combines **your research prompt**, **the AxonX Skill**, and **an Agent with code and service access**:

1. **Define the exploration.** Specify the baseline, hypothesis, data, evaluation windows, metrics, and execution target.
2. **Implement the research.** The Agent reads the Skill and relevant source, writes or optimizes plugin code, registers Tasks, and validates the implementation.
3. **Execute through the Harness.** Install the plugin in the selected service environment, inspect Task definitions, submit experiments, and wait for each upstream stage to succeed.
4. **Inspect and iterate.** Read logs, metadata, and artifacts; compare candidates under declared controls; revise code or parameters and preserve the evidence.

Example exploration prompt:

> Read the AxonX Skill and the qlib_a158 implementation. Develop a separate research plugin to investigate whether
> residual volatility and downside risk improve Alpha158 ranking. Use only information available at signal time.
> Keep the data snapshot, labels, training parameters, evaluation windows, and trading costs fixed for factor
> ablations. Implement and test the quantitative code, register and install the plugin, and run ETL, training,
> prediction, and backtest Tasks through AxonX. Preserve Task/Run IDs and report RankIC, net returns, drawdown,
> turnover, and limitations. Select candidates within the development window and reserve an independent confirmation window.

You can also ask the Agent to optimize an existing plugin's feature calculation, training procedure, or portfolio
policy. Specify whether the goal is runtime efficiency, signal quality, or trading performance, and how to evaluate it.

| Agent          | Development setup                                                                                                                                                                      | Research access                                                                                              |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| External Agent | Load [AxonX Skill](skills/axonx/SKILL.md) in Codex, Claude Code, or another host; provide the source checkout and code tools.                                                          | Use the `axonx` CLI or connect to the service through MCP. The host supplies model credentials.              |
| Built-in Agent | Configure model credentials and open **Studio → Agent**; provide the Skill or enable the bundled development guide, and configure `cwd` and development tools for the source checkout. | Use configured Job tools or the CLI through available command tools; the service supplies model credentials. |

The Skill can be read directly or installed using your Agent host's supported mechanism. Its source paths refer to an
AxonX checkout; a package installation alone does not include the example plugin sources. See the
[development and operations guide](docs/en/dev_guide.md) for contracts and commands.

### Connect an external Agent through MCP

Start AxonX, then configure your Agent host:

| Parameter             | Value                                         |
| --------------------- | --------------------------------------------- |
| URL                   | `http://127.0.0.1:1024/mcp`                   |
| Transport             | Streamable HTTP                               |
| Authentication header | `Authorization: Bearer <AxonX service token>` |

Use the connected service's token and adjust the address for custom ports or remote services.
See [MCP integration](https://flowllm-ai.github.io/AxonX/en/agent/mcp-integration).

### Configure the built-in Agent

The default backend uses the Claude Agent SDK. Add your provider's credentials, Claude-compatible URL, and model name
to `.env`, then restart the service:

```dotenv
CLAUDE_CODE_API_KEY=your-model-api-key
CLAUDE_CODE_BASE_URL=https://api.anthropic.com
CLAUDE_CODE_MODEL_NAME=your-model-name
```

To load the bundled English development guide:

```bash
axonx start --components.agent.default.load_dev_guide true --language en
```

Guide loading defaults to `false` and is separate from tool configuration. The default Job bridge exposes task and
artifact queries. For development, configure source access and SDK file/command tools; use the CLI or add the required
Jobs to `job_tools` for installation and submission. See [Agent configuration](https://flowllm-ai.github.io/AxonX/en/agent/configuration).

<a id="alpha158-and-the-plugin-system"></a>

## 🧩 From Qlib Alpha158 to extensible research plugins

The research chain is **ETL → Train → Predict → Backtest**, with factor analysis branching independently from ETL.
Three plugins progressively reuse implementations and artifacts:

| Plugin                                           | Research capabilities                                                    | Extension                                                                                                          |
| ------------------------------------------------ | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| [qlib_a158](plugins/qlib_a158/README.md)         | 158 price/volume features, LightGBM, factor analysis, and TopN backtests | Adapts Qlib Alpha158 into AxonX Tasks.                                                                             |
| [qlib_factor](plugins/qlib_factor/README.md)     | 13 optional market-moment, neutral-momentum, and risk features           | Extends ETL and training; reuses prediction and backtesting. Training still defaults to the 158 baseline features. |
| [qlib_strategy](plugins/qlib_strategy/README.md) | Minimum holding periods, rank retention, and replacement limits          | Reuses predictions and the stock backtest ledger without retraining.                                               |

The baseline uses Tushare data and adapts the universe, labels, training, and trading protocol; see
[Differences from original Qlib](plugins/qlib_a158/README.md#differences-from-original-qlib).
Plugin registration, Task contracts, and artifact requirements are covered in the [development guide](docs/en/dev_guide.md).

<a id="benchmark-agent-developed-market-cross-sectional-features"></a>

## 📊 Alpha158 improvement case: factors and portfolio strategy

The experiment compares the Alpha158 baseline, a model with two added risk factors, and a portfolio strategy
that reuses the factor-model predictions:

| Configuration           | Quantitative change                                                                                       | Top20 net annualized | Net Sharpe | Max drawdown | Daily two-sided turnover |
| ----------------------- | --------------------------------------------------------------------------------------------------------- | -------------------: | ---------: | -----------: | -----------------------: |
| Alpha158 baseline       | 158 features; fixed 1-day holding                                                                         |                7.67% |     0.3619 |      -38.65% |                  198.83% |
| Risk-factor model       | Add 20-day residual volatility and downside risk; 160 features                                            |                9.03% |     0.4052 |      -40.69% |                  199.35% |
| Rank-retention strategy | Reuse factor predictions; minimum 3-day holding, rank retention, 20% daily replacement count cap per side |               32.37% |     1.1575 |      -24.91% |                   40.01% |

Training covers `[20150101,20230101)`; evaluation covers `20230103–20261008`, or 909 market dates. Buy/sell fees are
0.05% / 0.15%. The replacement cap limits stock counts, not transaction notional; initial construction is exempt.
The strategy plugin's default minimum holding period is 10 days; this experiment explicitly uses 3.

![Signal quality](docs/figures/benchmark/qlib-signal-quality.svg)

![Portfolio performance](docs/figures/benchmark/qlib-topn-results.svg)

**Evidence limits:** the three configurations were rerun on 2026-10-10, but have no independent confirmation window.
Base/factor `feature_fraction` is 0.9/1.0, so differences do not isolate the added factors. All three backtests report
`incomplete_market_data`; fills use same-close quote proxies and 2026 is a partial year. These results describe the
adapted AxonX experiments and do not establish outperformance over the original Qlib benchmark.

[Full settings, metrics, reproduction commands, and Task provenance](docs/en/research/experiments.md#comparison).

<a id="quick-start"></a>

## 🚀 Quick start

Requires **Python 3.12+**; local Task execution supports **macOS and Linux**.

### Install and start

```bash
pip install "axonx[studio]"
# Optional: install the Alpha158 plugin in the service environment
pip install axonx-qlib-a158
```

Create `.env` in the startup directory with your local service token:

```dotenv
AXONX_SERVICE_TOKEN=replace-with-your-local-service-token
```

```bash
axonx start
```

The CLI loads `.env` from the current directory or a parent; existing environment variables take precedence.
Keep the service running and use another terminal for subsequent commands. See [example.env](example.env) for model,
market-data, and remote settings; see [CONTRIBUTING.md](CONTRIBUTING.md) for source development and Studio builds.
Restart the service after direct pip installation or editable source changes.

### Open Studio

Visit `http://127.0.0.1:1024/` and enter `AXONX_SERVICE_TOKEN` in **Settings → Local service token**.
See the [Studio guide](docs/en/getting-started/studio.md) for Tasks, research charts, and the Agent workspace.

<table>
  <tr><th width="50%">Home</th><th width="50%">Task management</th></tr>
  <tr>
    <td><a href="docs/figures/studio/home.png"><img src="docs/figures/studio/home.png" alt="AxonX Studio home" width="100%" /></a></td>
    <td><a href="docs/figures/studio/task-list.png"><img src="docs/figures/studio/task-list.png" alt="AxonX Studio task management" width="100%" /></a></td>
  </tr>
</table>

<a id="quick-demo"></a>

### Verify your first Task

The built-in demo requires no market-data or model credentials:

```bash
axonx submit --task demo --x 2 --y 3
axonx wait_task --task-id '<returned_task_id>' --run-id '<returned_run_id>' --client-timeout 120
axonx get_task_context --task-id '<returned_task_id>'
```

Use `answer.task_id` and `answer.run_id` returned by `submit`, and wait for `succeeded` before reading outputs or
submitting downstream Tasks. `source_tasks` records lineage; it does not automatically run the DAG.

For Alpha158, configure `AXONX_TUSHARE_TOKEN` and prepare enough historical data, then run the stages in the
[research workflow](docs/en/research/workflow.md). Full commands for the three-version experiment are in the
[reproduction guide](docs/en/research/experiments.md#comparison).

<a id="axonx-cli-commands-and-remote-execution"></a>

## 🛠️ CLI and remote execution

See the [CLI reference](docs/en/reference/cli.md) for definitions, progress, and logs, and
[plugin management](docs/en/plugins/management.md) for installation and updates.

### Connect directly to a remote service with the CLI

Set the target service's `AXONX_TARGET_TOKEN` and use the same `--target` for installation, submission, waiting, and queries:

```bash
axonx plugin install ./plugins/qlib_factor --target 'http://<host>:1024'
axonx get_task_definition --task qlib_factor_train --target 'http://<host>:1024'
```

An explicit `--target` uses `AXONX_TARGET_TOKEN` by default; default local calls use `AXONX_SERVICE_TOKEN`.
Without a target, plugin commands use the current Python environment.

### Use remote machines in Studio

Set `AXONX_TARGET` and `AXONX_TARGET_TOKEN` in the local service environment, run `axonx start --config remote`,
and select the machine in Studio. The target service owns its plugins, data, and workspace;
see [remote machines](docs/en/guides/remote-machines.md) for multiple-target configuration.

<a id="axonx-documentation"></a>

## 📚 Documentation

| Goal                     | Start here                                                                                                                                                                      |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Install and run research | [Quickstart](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart) · [Research workflow](docs/en/research/workflow.md)                                              |
| Develop with an Agent    | [AxonX Skill](skills/axonx/SKILL.md) · [Agent integration](docs/en/agent/external.md) · [Built-in configuration](docs/en/agent/configuration.md)                                |
| Implement plugins        | [Task development](docs/en/dev_guide.md) · [Plugin management](docs/en/plugins/management.md) · [Artifact contracts](docs/en/reference/research-artifacts.md)                   |
| Understand the Harness   | [Architecture](docs/en/concepts/architecture.md) · [Jobs and Tasks](docs/en/concepts/jobs-and-tasks.md) · [Framework extensions](docs/en/development/framework-extensions.md)   |
| Evaluate results         | [Experiment design](docs/en/research/experiments.md) · [Backtest interpretation](docs/en/research/backtest.md) · [Strategy comparison](docs/en/research/strategy-comparison.md) |
| Operate services         | [CLI reference](docs/en/reference/cli.md) · [Configuration](docs/en/reference/configuration.md) · [Remote execution](docs/en/guides/remote-machines.md)                         |

[English documentation](https://flowllm-ai.github.io/AxonX/en/docs) · [中文文档](https://flowllm-ai.github.io/AxonX/zh/docs)

<a id="contributing"></a>

## 💬 Contributing

Contributions to the Harness, research plugins, experiment evidence, and documentation are welcome.
See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and checks, and [GitHub issues](https://github.com/FlowLLM-AI/AxonX/issues)
for bugs and proposals. Keep algorithms in plugins, preserve public contracts, update both documentation languages,
and include reproducible settings and artifacts when contributing research results.

<a id="license"></a>

## ⚖️ License

[Apache License 2.0](LICENSE).
