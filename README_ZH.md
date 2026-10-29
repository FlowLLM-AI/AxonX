<p align="center">
  <img src="https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/axonx_studio/public/axonx-logo.svg" alt="AxonX" width="560" />
</p>

<p align="center"><strong>从研究 Prompt 到量化代码，再到可追溯的实验。</strong></p>

<p align="center">
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&amp;logoColor=white&amp;style=flat-square" alt="Python 3.12+" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/v/axonx?logo=pypi&amp;logoColor=white&amp;style=flat-square" alt="PyPI 版本" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/dm/axonx?label=downloads%2Fmonth&amp;style=flat-square&amp;logo=pypi&amp;logoColor=white" alt="PyPI 每月下载量" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/m/FlowLLM-AI/AxonX?label=commits%2Fmonth&amp;style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub 每月提交活动" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/graphs/traffic"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fflowllm-ai.github.io%2FAxonX%2Fbadges%2Fclones.json&amp;style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub 最近 14 天 Clone 次数" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/forks"><img src="https://img.shields.io/github/forks/FlowLLM-AI/AxonX?label=forks&amp;style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub Fork 总数" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square&amp;logo=apache&amp;logoColor=white" alt="Apache License 2.0" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/zh/concepts/architecture"><img src="https://img.shields.io/badge/access-CLI%20%2F%20MCP-6366f1?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMyA0aDE4djE2SDN6IE03IDhsNCA0LTQgNCBNMTMgMTZoNCIvPjwvc3ZnPg%3D%3D&amp;logoColor=white" alt="CLI 和 MCP 接入" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/zh/docs"><img src="https://img.shields.io/badge/docs-AxonX-blue?style=flat-square&amp;logo=readthedocs&amp;logoColor=white" alt="AxonX 中文文档" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/README.md"><img src="https://img.shields.io/badge/English-Read-yellow?style=flat-square&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/README_ZH.md"><img src="https://img.shields.io/badge/%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-%E9%98%85%E8%AF%BB-orange?style=flat-square&amp;logo=googletranslate&amp;logoColor=white" alt="阅读简体中文" /></a>
  <a href="https://deepwiki.com/FlowLLM-AI/AxonX"><img src="https://img.shields.io/badge/DeepWiki-Ask_Devin-navy?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMyA0aDZsMyAyIDMtMmg2djE2aC02bC0zIDItMy0ySDN6IE0xMiA2djE2Ii8%2BPC9zdmc%2B&amp;logoColor=white" alt="通过 DeepWiki 了解 AxonX" /></a>
</p>

<p align="center">⭐ <a href="https://github.com/FlowLLM-AI/AxonX">给 AxonX 点个 GitHub Star</a>！</p>

<a id="axonx-是什么"></a>

## 🧠 AxonX 是什么？

**AxonX 是面向 Agent 的量化研究 Harness。** Agent 开发研究插件、执行实验，与研究者共同检查参数、日志、依赖和产物。

**用户提出问题，Agent 实现逻辑，AxonX 管理执行与证据。** 支持 CLI、HTTP、MCP 和 Studio。参考插件适配 [Microsoft Qlib](https://github.com/microsoft/qlib) 的 Alpha158 基线，扩展可配置因子与持仓策略。

[快速开始](#快速开始) · [插件体系](#alpha158-与插件系统) · [研究案例](#benchmark-agent-开发市场横截面增强特征) · [文档](#axonx-文档) · <a href="https://flowllm-ai.github.io/AxonX/playground/?lang=zh" target="_self">Playground 在线试玩</a>

<a id="为什么使用-axonx"></a>

## ✨ 为什么使用 AxonX？

- **使用 Agent 开发：** 结合 [AxonX Skill](skills/axonx/SKILL.md)、源码工具和实时 Task Schema。
- **保留实验依据：** 类型化输入输出、进程身份、日志和带修订的产物引用。
- **通过 Studio 检查：** 任务控制、工作区预览、研究图表与策略比较。

## 📰 最新更新

- **发布 0.3.0：** 支持可继承配置、统一任务执行，以及服务重启不中断的定时任务。
- **Alpha158 实验：** 风险因子与排名保留策略的 Top20 净年化收益，相比适配基线分别提升 **+1.36 pp 和 +24.70 pp**。见[结果与证据边界](#benchmark-agent-开发市场横截面增强特征)。
- **Studio Playground：** 使用模拟数据体验任务和图表。<a href="https://flowllm-ai.github.io/AxonX/playground/?lang=zh" target="_self">在线试玩</a>。

![AxonX 使用入口、服务命令与核心能力](docs/figures/getting-started/overview.svg)

<a id="快速开始"></a>

## 🚀 快速开始

当前源码版本为 **AxonX 0.3.1**，要求 **Python 3.12+，支持 macOS 和 Linux**。Studio 是独立发布的可选包。

### 1. 安装与启动

从 pip 安装：

```bash
pip install 'axonx[studio]'
```

或从源码安装后端与 Studio：

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e ./axonx_studio -e '.[studio]'
npm --prefix axonx_studio ci
npm --prefix axonx_studio run build
```

源码安装使用 editable 模式。构建 Studio 需要 **Node.js 22.13+（22.x）、24.x 或 26+**；修改前端后需重新构建。

然后启动服务：

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

默认端口 `1024`、工作区 `.axonx`、服务/CLI 日志目录 `logs/`。可选设置见 [example.env](example.env)；CLI 启动时从启动目录或父目录加载最近的 `.env`，保留已有环境变量。保持此终端运行，在另一终端使用相同 Python 环境与 token。

需要自定义设置时，将以下 YAML 保存为 `axonx.local.yaml`：

```yaml
extends: default
workspace_dir: .axonx
service:
  host: 127.0.0.1
```

通过 `axonx app --config ./axonx.local.yaml` 启动。自定义配置仅在声明 `extends: default` 时继承内置服务、组件和 Job；字典合并，列表和标量替换。已安装插件也可提供命名配置，详见[配置参考](docs/zh/reference/configuration.md)。

<a id="快速演示"></a>

### 2. 运行 Demo 并打开 Studio

```bash
axonx get_task_def --task demo
axonx exec --task demo --task-name quickstart --x 2 --y 3
axonx status --task-id 'base#demo#quickstart' --detail full
```

`exec` 等待完成，输出业务结果（`result=5`）并返回 Task 退出码。Demo 无需行情或模型凭据。访问 `http://127.0.0.1:1024/`，在 **设置 → 本机服务 token** 填写令牌。

`axonx --help` 显示离线用法，`axonx help` 查询运行中服务的 Job。执行设置按 **显式 CLI 参数 → 服务 `get_config` → 内置默认值** 生效。仅在服务连接不可用时回退；认证或服务错误直接报告。Task 专用参数通过 `get_task_def` 查询。

记录 Task ID 和 metadata `started_at`。实验使用不同实例名：同名重跑替换当前记录与输出，保留 `persistent/`。详见[任务管理](docs/zh/guides/task-management.md)。

<a id="agent-接入与开发指南"></a>

### 3. 使用 Agent 开发

使用参考研究插件时，复用上面的源码仓库；通过 pip 安装的用户可另行克隆仓库。在仓库根目录，将插件安装到执行服务的 Python 环境：

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx restart_service
```

研究插件从源码安装，扩展按 **Alpha158 → factor → strategy** 顺序安装。源码变化后重启常驻服务；依赖或入口点变化后重新安装。服务重新就绪后再查询定义。

提供源码、文件/命令工具和 [AxonX Skill](skills/axonx/SKILL.md)。通过 GitHub CLI 从 `main` 安装 Skill，Claude Code 将 `--agent` 改为 `claude-code`：

```bash
gh skill install FlowLLM-AI/AxonX axonx --agent codex --scope user --pin main
```

按上文安装 AxonX 和研究插件，再选择接入方式：

- **外部 Agent：** 客户端管理模型凭据。使用 CLI，或通过 Streamable HTTP MCP 连接 `http://127.0.0.1:1024/mcp`，携带 `Authorization: Bearer <token>`。见 [MCP 集成](docs/zh/agent/mcp-integration.md)。
- **内置 Agent：** 配置以下模型环境，重启服务后打开 **Studio → Agent**，将其 `cwd` 指向源码。见 [Agent 配置](docs/zh/agent/configuration.md)。

```dotenv
CLAUDE_CODE_API_KEY=your-model-api-key
CLAUDE_CODE_BASE_URL=https://api.anthropic.com
CLAUDE_CODE_MODEL_NAME=your-model-name
```

向 Agent 提出明确目标，例如：

> 阅读 AxonX Skill 和 Alpha158 实现，开发独立插件测试残差波动与下行风险。固定数据、训练设置、成本和评估窗口，仅使用信号时点可得信息。测试代码并执行实验，报告 Task ID、RankIC、净收益、回撤与限制，预留独立确认窗口。

开始前准备历史数据与 `AXONX_TUSHARE_TOKEN`，再按[研究流程](docs/zh/research/workflow.md)执行。

<a id="alpha158-与插件系统"></a>

## 🧩 从 Qlib Alpha158 到研究插件

主链为 **ETL → Train → Predict → Backtest**，因子分析可从 ETL 分支。`qlib_a158_research` 组合各阶段，叶子 Task 可复用兼容的上游产物。

| 插件                                                | 能力                                           |
| --------------------------------------------------- | ---------------------------------------------- |
| [qlib_a158](plugins/qlib_a158/README_ZH.md)         | 158 个价量特征、LightGBM、因子分析与 TopN 回测 |
| [qlib_factor](plugins/qlib_factor/README_ZH.md)     | 13 个可选特征，训练默认使用 158 个基线特征     |
| [qlib_strategy](plugins/qlib_strategy/README_ZH.md) | 最短持有期、排名保留与换仓限制，复用预测       |

其他研究方法通过同一套 [Task 与插件契约](docs/zh/dev_guide.md)接入。基线调整了 Qlib 的数据、标签、训练与交易假设，详见[与原始 Qlib 的差异](plugins/qlib_a158/README_ZH.md#与原始-qlib-的差异)。

<a id="benchmark-agent-开发市场横截面增强特征"></a>

## 📊 Alpha158 改进案例

该历史实验增加两个风险特征，再对因子模型的预测应用排名保留策略：

| 配置          | Top20 净年化 | 最大回撤 | 日均双边换手 |
| ------------- | -----------: | -------: | -----------: |
| Alpha158 基线 |        7.67% |  -38.65% |      198.83% |
| 风险因子模型  |        9.03% |  -40.69% |      199.35% |
| 排名保留策略  |       32.37% |  -24.91% |       40.01% |

训练：`[20150101,20230101)`；评估：`20230103–20261008`（909 个市场日）。买入/卖出费用：0.05% / 0.15%。策略最短持有 3 日，每日每侧换仓数量上限 20%，首次建仓除外。

![信号质量](docs/figures/benchmark/qlib-signal-quality.svg)

![组合表现](docs/figures/benchmark/qlib-topn-results.svg)

**证据边界：** 尚无独立确认窗口；基础/因子模型的 `feature_fraction` 不同（0.9/1.0），无法单独归因于新增因子。所有回测均报告 `incomplete_market_data`，使用同收盘成交代理，且 2026 年不完整。不能据此认定优于原始 Qlib。

[完整设定、复现命令与历史任务来源](docs/zh/research/alpha158-case.md)。

<a id="axonx-cli-命令与远程执行"></a>

## 🛠️ CLI 与远程执行

设置目标令牌，执行与观察使用相同地址：

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx exec --task demo --task-name remote-check --x 2 --y 3 --target node-b:1024
axonx status --task-id 'base#demo#remote-check' --detail full --target node-b:1024
```

替换示例地址。`--target` 使用 `AXONX_TARGET_TOKEN`，默认本机调用使用 `AXONX_SERVICE_TOKEN`。远程路径属于目标机。本地插件部署按 **构建 → 上传 → 安装 `location` → 清理 `path` → 重启/验证** 完成，见[插件管理](docs/zh/plugins/management.md)。

Studio 使用后端配置的 `targets`；`AXONX_TARGET` 填充内置 `remote` 配置，本身不会选择 CLI 目标。见[远程机器](docs/zh/guides/deployment.md#远程接入)。服务重启会停止服务拥有的手动命令，保留 Daemon 拥有的定时 Task；计划接受本地 `axonx exec --task NAME` 命令。见[服务更新](docs/zh/guides/operations.md#服务更新与重启)。

<a id="axonx-文档"></a>

## 📚 文档入口

| 目标             | 指南                                                                                                                    |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 运行研究         | [快速开始](docs/zh/getting-started/quickstart.md) · [研究流程](docs/zh/research/workflow.md)                            |
| 使用 Agent       | [外部 Agent](docs/zh/agent/overview.md) · [内置 Agent](docs/zh/agent/configuration.md)                                  |
| 开发插件         | [开发指南](docs/zh/dev_guide.md) · [产物契约](docs/zh/reference/research-artifacts.md)                                  |
| 评估结果         | [实验设计](docs/zh/research/experiments.md) · [策略比较](docs/zh/research/strategy-comparison.md)                       |
| 运行或扩展 AxonX | [CLI](docs/zh/reference/cli.md) · [配置](docs/zh/reference/configuration.md) · [架构](docs/zh/concepts/architecture.md) |

[中文文档](https://flowllm-ai.github.io/AxonX/zh/docs) · [English documentation](https://flowllm-ai.github.io/AxonX/en/docs)

<a id="参与贡献"></a>

## 💬 参与贡献

欢迎贡献框架、插件、实验与文档。环境与检查要求见[贡献指南](CONTRIBUTING_ZH.md)，问题和提案见 [GitHub Issues](https://github.com/FlowLLM-AI/AxonX/issues)。

<a id="许可证"></a>

## ⚖️ 许可证

[Apache License 2.0](LICENSE)。
