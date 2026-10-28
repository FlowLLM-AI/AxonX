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

**AxonX is an agent-native harness for quantitative research.** Agents develop research plugins, execute experiments, and inspect the same parameters, logs, dependencies and artifacts as researchers.

**You define the question; the Agent implements it; AxonX manages execution and evidence.** Use CLI, HTTP, MCP or Studio. The reference plugins adapt [Microsoft Qlib](https://github.com/microsoft/qlib)'s Alpha158 baseline with configurable factors and portfolio policies.

[Quick start](#quick-start) · [Plugins](#alpha158-and-the-plugin-system) · [Case study](#benchmark-agent-developed-market-cross-sectional-features) · [Documentation](#axonx-documentation) · <a href="https://flowllm-ai.github.io/AxonX/playground/?lang=en" target="_self">Try Playground</a>

<a id="why-axonx"></a>

## ✨ Why AxonX?

- **Develop with Agents:** use the [AxonX Skill](skills/axonx/SKILL.md), source tools and live Task schemas.
- **Keep traceable experiments:** typed inputs/outputs, process identity, logs and versioned artifact references.
- **Inspect in Studio:** Task control, workspace previews, research charts and strategy comparisons.

## 📰 Latest Updates

- **CLI Task execution:** `exec` waits for completion and returns business output plus the Task exit code; remote execution uses the service's `cli` Job. Daemon-owned scheduled Tasks continue across service restarts. See [Jobs and Tasks](docs/en/concepts/jobs-and-tasks.md) and [scheduling](docs/en/guides/scheduling.md).
- **Alpha158 experiments:** risk factors and rank retention improved Top20 net annualized returns by **+1.36 pp and +24.70 pp** over the adapted baseline. See [results and evidence limits](#benchmark-agent-developed-market-cross-sectional-features).
- **Studio Playground:** explore Tasks and charts with simulated data. <a href="https://flowllm-ai.github.io/AxonX/playground/?lang=en" target="_self">Try it online</a>.

![AxonX research and execution overview](docs/figures/getting-started/overview.svg)

<a id="quick-start"></a>

## 🚀 Quick start

Requires **Python 3.12+ on macOS or Linux**.

### 1. Install and start

Install from pip:

```bash
pip install 'axonx[studio]'
```

Or install the backend and Studio from source:

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e ./axonx_studio -e '.[studio]'
npm --prefix axonx_studio ci
npm --prefix axonx_studio run build
```

The source install uses editable packages. Building Studio requires **Node.js 22.13+ (22.x), 24.x or 26+**; rebuild after frontend changes.

Then start the service:

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

Defaults: port `1024`, workspace `.axonx`. Settings can also come from `.env`; existing environment variables take precedence. Keep this terminal open and use another with the same Python environment and token.

<a id="quick-demo"></a>

### 2. Run Demo and open Studio

```bash
axonx get_task_def --task demo
axonx exec --task demo --task-name quickstart --x 2 --y 3
axonx status --task-id 'base#demo#quickstart' --detail full
```

`exec` waits and returns business output (`result=5`) plus the Task exit code. Demo needs no market data or model credentials. Open `http://127.0.0.1:1024/` and enter the token in **Settings → Local service token**.

Keep the Task ID and metadata `started_at`. Use different instance names to preserve experiments: same-name reruns replace current records and outputs, retaining `persistent/`. See [Task management](docs/en/guides/task-management.md).

<a id="agent-access-and-development-guides"></a>

### 3. Develop with an Agent

For the reference research plugins, use the source checkout above (or clone the repository if you installed from pip). From the repository root, install into the execution service's Python environment:

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx restart_service
```

Research plugins are installed from source. Install extensions in **Alpha158 → factor → strategy** order. Restart persistent services after code changes; reinstall after dependency or entry-point changes. Wait for the service to be ready before querying definitions.

Provide the checkout, file/command tools and [AxonX Skill](skills/axonx/SKILL.md). Choose an access path:

- **External Agent:** the host manages model credentials. Use CLI or Streamable HTTP MCP at `http://127.0.0.1:1024/mcp` with `Authorization: Bearer <token>`. See [MCP integration](docs/en/agent/mcp-integration.md).
- **Built-in Agent:** set the following model environment, restart the service, and open **Studio → Agent**. Configure its `cwd` for the checkout; see [Agent configuration](docs/en/agent/configuration.md).

```dotenv
CLAUDE_CODE_API_KEY=your-model-api-key
CLAUDE_CODE_BASE_URL=https://api.anthropic.com
CLAUDE_CODE_MODEL_NAME=your-model-name
```

Give the Agent a concrete objective, for example:

> Read the AxonX Skill and Alpha158 implementation. Develop a separate plugin to test residual volatility and downside risk. Fix data, training settings, costs and evaluation windows; use only signal-time information. Test the code, run experiments, and report Task IDs, RankIC, net returns, drawdown and limitations. Reserve an independent confirmation window.

Prepare historical data and `AXONX_TUSHARE_TOKEN` before following the [research workflow](docs/en/research/workflow.md).

<a id="alpha158-and-the-plugin-system"></a>

## 🧩 From Qlib Alpha158 to research plugins

The main chain is **ETL → Train → Predict → Backtest**, with optional factor analysis from ETL. `qlib_a158_research` composes these stages; leaf Tasks can reuse compatible upstream artifacts.

| Plugin                                           | Capability                                                                         |
| ------------------------------------------------ | ---------------------------------------------------------------------------------- |
| [qlib_a158](plugins/qlib_a158/README.md)         | 158 price/volume features, LightGBM, factor analysis and TopN backtests            |
| [qlib_factor](plugins/qlib_factor/README.md)     | 13 optional features; training defaults to the 158-feature baseline                |
| [qlib_strategy](plugins/qlib_strategy/README.md) | Minimum holding periods, rank retention and replacement limits; reuses predictions |

Other research methods use the same [Task and plugin contracts](docs/en/dev_guide.md). The baseline adapts Qlib's data, labels, training and trading assumptions; see [differences from original Qlib](plugins/qlib_a158/README.md#differences-from-original-qlib).

<a id="benchmark-agent-developed-market-cross-sectional-features"></a>

## 📊 Alpha158 improvement case

This recorded experiment adds two risk features, then applies a rank-retention policy to the factor-model predictions:

| Configuration           | Top20 net annualized | Max drawdown | Daily two-sided turnover |
| ----------------------- | -------------------: | -----------: | -----------------------: |
| Alpha158 baseline       |                7.67% |      -38.65% |                  198.83% |
| Risk-factor model       |                9.03% |      -40.69% |                  199.35% |
| Rank-retention strategy |               32.37% |      -24.91% |                   40.01% |

Training: `[20150101,20230101)`; evaluation: `20230103–20261008` (909 market dates). Buy/sell fees: 0.05% / 0.15%. The strategy uses a 3-day minimum holding period and a 20% replacement count cap per side; initial construction is exempt.

![Signal quality](docs/figures/benchmark/qlib-signal-quality.svg)

![Portfolio performance](docs/figures/benchmark/qlib-topn-results.svg)

**Evidence limits:** no independent confirmation window; base/factor `feature_fraction` differs (0.9/1.0), so results do not isolate the added factors. All backtests report `incomplete_market_data`, use same-close fill proxies and include a partial 2026. These results do not establish outperformance over original Qlib.

[Full settings, reproduction commands and historical Task provenance](docs/en/research/alpha158-case.md).

<a id="axonx-cli-commands-and-remote-execution"></a>

## 🛠️ CLI and remote execution

Set the destination token and keep the same target for execution and observation:

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx exec --task demo --task-name remote-check --x 2 --y 3 --target node-b:1024
axonx status --task-id 'base#demo#remote-check' --detail full --target node-b:1024
```

Replace the example address. `--target` uses `AXONX_TARGET_TOKEN`; default local calls use `AXONX_SERVICE_TOKEN`. Remote paths belong to the target. Deploy local plugins by **build → upload → install `location` → clean `path` → restart/verify**; see [plugin management](docs/en/plugins/management.md).

Studio uses backend-configured `targets`; see [remote machines](docs/en/guides/remote-machines.md). Service restarts stop service-owned manual commands and preserve daemon-owned scheduled Tasks; see [service updates](docs/en/guides/self-update.md).

<a id="axonx-documentation"></a>

## 📚 Documentation

| Goal                    | Guide                                                                                                                                    |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Run research            | [Quickstart](docs/en/getting-started/quickstart.md) · [Research workflow](docs/en/research/workflow.md)                                  |
| Use an Agent            | [External Agents](docs/en/agent/external.md) · [Built-in Agent](docs/en/agent/configuration.md)                                          |
| Develop plugins         | [Development guide](docs/en/dev_guide.md) · [Artifact contracts](docs/en/reference/research-artifacts.md)                                |
| Evaluate results        | [Experiment design](docs/en/research/experiments.md) · [Strategy comparison](docs/en/research/strategy-comparison.md)                    |
| Operate or extend AxonX | [CLI](docs/en/reference/cli.md) · [Configuration](docs/en/reference/configuration.md) · [Architecture](docs/en/concepts/architecture.md) |

[English documentation](https://flowllm-ai.github.io/AxonX/en/docs) · [中文文档](https://flowllm-ai.github.io/AxonX/zh/docs)

<a id="contributing"></a>

## 💬 Contributing

Contributions to the framework, plugins, experiments and documentation are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and checks, or [GitHub issues](https://github.com/FlowLLM-AI/AxonX/issues) for bugs and proposals.

<a id="license"></a>

## ⚖️ License

[Apache License 2.0](LICENSE).
