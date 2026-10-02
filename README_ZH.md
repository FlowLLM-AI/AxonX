<p align="center">
  <img src="axonx_studio/public/axonx-logo.svg" alt="AxonX" width="560" />
</p>

<p align="center"><strong>面向金融量化研究的 Agent Harness。</strong></p>

<p align="center">
  <a href="README.md">English</a> · 简体中文<br />
  <a href="https://flowllm-ai.github.io/AxonX/zh/">项目首页</a> ·
  <a href="https://flowllm-ai.github.io/AxonX/zh/docs">文档</a> ·
  <a href="https://github.com/FlowLLM-AI/AxonX/issues">问题反馈</a> ·
  <a href="CONTRIBUTING_ZH.md">参与贡献</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue" alt="Python 3.12+" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-blue" alt="Apache License 2.0" /></a>
</p>

## AxonX 是什么？

AxonX 将研究代码、任务执行、日志和结果连接到同一个工作区。它把数据处理、因子分析、训练、预测和回测表示为具有明确输入输出契约的 Task，让 CLI、Studio 和 Agent 通过 Job 接口访问同一套能力。

研究者可以检查结果如何产生、复用上游数据、比较实验，并让 Agent 查询任务和产物。插件作者提供研究算法，AxonX 提供执行与检查基础设施。目前 AxonX 处于 alpha 阶段。

## 为什么使用 AxonX？

- **研究任务有明确契约。** 类型化输入输出描述每个 Task 消费和产生的内容。→ [Task 契约](https://flowllm-ai.github.io/AxonX/zh/reference/task-contracts)
- **执行过程可检查。** 将 Task 提交到独立 worker 进程，跟踪状态、进度、日志和结果。→ [任务管理](https://flowllm-ai.github.io/AxonX/zh/guides/task-management)
- **实验来源可追踪。** 工作区同时保存参数、产物和上游 Task ID，便于检查与复用。→ [任务血缘](https://flowllm-ai.github.io/AxonX/zh/concepts/task-lineage)
- **CLI、Studio 和 Agent 共用工作流程。** 使用脚本、浏览器表单与图表，或通过已配置工具读取任务证据的助手。→ [Studio](https://flowllm-ai.github.io/AxonX/zh/getting-started/studio) · [Agent](https://flowllm-ai.github.io/AxonX/zh/agent/usage)
- **插件扩展与远程执行。** 将研究能力打包为插件，并明确选择远程执行目标。→ [插件管理](https://flowllm-ai.github.io/AxonX/zh/guides/plugin-management) · [远程机器](https://flowllm-ai.github.io/AxonX/zh/guides/remote-machines)

## Studio

Studio 提供任务提交、运行详情、机器资源、工作区浏览和研究结果视图。

![AxonX Studio 首页](docs/figures/studio/home.png)

安装和连接方式见 [Studio 入门](https://flowllm-ai.github.io/AxonX/zh/getting-started/studio)。

## 快速开始

要求 **Python 3.12+**，本地 TaskManager 支持 **macOS 和 Linux**。从源码安装：

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### 运行第一个 Task

内置 Demo 对两个整数求和，无需服务、行情数据或模型凭据：

```bash
axonx exec --task demo --task-name first-demo --x 2 --y 3
```

命令打印 Task 输出，其中 `result` 为 `5`。任务记录保存在当前目录的 `.axonx/` 下，日志使用 `logs/`。需要保留不同实验时，使用不同任务名或省略 `--task-name`；复用名字会替换已结束的 Task 目录。

### 通过服务提交

在终端 A 设置自己的服务 token，启动本地服务：

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx start --service.host 127.0.0.1
```

在终端 B 激活同一环境，设置与服务相同的 token：

```bash
source .venv/bin/activate
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx get_task_definition --task demo
axonx submit --task demo --task-name submitted-demo --x 2 --y 3
```

保留提交响应中的 `answer.run_id`，用真实值替换下面的占位符：

```bash
axonx wait_task --task-id 'base#demo#submitted-demo' \
  --run-id '<actual returned run_id>' --client-timeout 120
axonx status --task-id 'base#demo#submitted-demo'
```

提交成功表示请求已接受。等待状态变为 `succeeded`，状态响应应包含 `result.result: 5`。默认服务端口为 `1024`。配置、日志和持久记录的完整说明见[快速开始](https://flowllm-ai.github.io/AxonX/zh/getting-started/quickstart)。

## 量化研究与插件

![AxonX 研究与执行总览](docs/figures/getting-started/overview.svg)

典型研究链路为 **原始数据 → ETL → 训练 → 预测 → 回测**，因子分析从 ETL 分支执行。任务通过 `source_tasks` 记录上游 ID，可以在不同实验间复用数据集和预测结果。每个阶段由用户或调用程序组织提交。

核心框架提供 Task 契约与运行基础设施，研究插件实现具体因子、模型和回测逻辑：

| 插件源码 | 用途 |
| --- | --- |
| [Alpha158](plugins/a158/) | Alpha158 研究任务实现 |
| [Alpha158 Enhanced](plugins/a158_enhanced/README.md) | 扩展的 Alpha158 研究任务与实验说明 |

插件安装和数据准备见[量化研究流程](https://flowllm-ai.github.io/AxonX/zh/research/workflow)。行情数据与 Agent 功能需要各自的服务商配置。收益定义、成本和交易假设见[回测解读](https://flowllm-ai.github.io/AxonX/zh/research/backtest)。

## 文档导航

| 我想要…… | 指南 |
| --- | --- |
| 安装并运行第一个 Task | [快速开始](https://flowllm-ai.github.io/AxonX/zh/getting-started/quickstart) |
| 在浏览器提交和检查任务 | [Studio 入门](https://flowllm-ai.github.io/AxonX/zh/getting-started/studio) |
| 运行研究链路并理解结果 | [量化研究流程](https://flowllm-ai.github.io/AxonX/zh/research/workflow) |
| 配置研究助手或外部 MCP 工具 | [Agent 配置](https://flowllm-ai.github.io/AxonX/zh/agent/configuration) · [MCP 集成](https://flowllm-ai.github.io/AxonX/zh/agent/mcp-integration) |
| 在其他机器执行任务 | [远程机器](https://flowllm-ai.github.io/AxonX/zh/guides/remote-machines) |
| 配置和调用 AxonX | [配置](https://flowllm-ai.github.io/AxonX/zh/reference/configuration) · [CLI](https://flowllm-ai.github.io/AxonX/zh/reference/cli) · [Python](https://flowllm-ai.github.io/AxonX/zh/reference/python) |
| 开发研究任务或扩展框架 | [开发指南](https://flowllm-ai.github.io/AxonX/zh/dev_guide) · [框架扩展](https://flowllm-ai.github.io/AxonX/zh/development/framework-extensions) |

浏览[完整文档](https://flowllm-ai.github.io/AxonX/zh/docs)。双语文档源码位于 [docs/](docs/README.md)。

## 参与贡献

欢迎问题反馈、功能建议、文档改进、研究插件和代码贡献。请先搜索[已有 Issues](https://github.com/FlowLLM-AI/AxonX/issues)，开发环境与检查要求见[贡献指南](CONTRIBUTING_ZH.md)。

## 许可证

AxonX 基于 [Apache License 2.0](LICENSE) 开源。
