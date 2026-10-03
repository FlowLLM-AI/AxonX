<p align="center">
  <img src="https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/axonx_studio/public/axonx-logo.svg" alt="AxonX" width="560" />
</p>

<p align="center"><strong>面向金融量化研究的 Agent Harness。</strong></p>

<p align="center">
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&amp;logoColor=white&amp;style=flat-square" alt="Python 3.12+" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/v/axonx?logo=pypi&amp;logoColor=white&amp;style=flat-square" alt="PyPI 版本" /></a>
  <a href="https://pypi.org/project/axonx/"><img src="https://img.shields.io/pypi/dm/axonx?label=downloads%2Fmonth&amp;style=flat-square&amp;logo=pypi&amp;logoColor=white" alt="PyPI 每月下载量" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/graphs/commit-activity"><img src="https://img.shields.io/github/commit-activity/m/FlowLLM-AI/AxonX?label=commits%2Fmonth&amp;style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub 每月提交活动" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square&amp;logo=apache&amp;logoColor=white" alt="Apache License 2.0" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/zh/concepts/architecture"><img src="https://img.shields.io/badge/access-CLI%20%2F%20MCP-6366f1?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMyA0aDE4djE2SDN6IE03IDhsNCA0LTQgNCBNMTMgMTZoNCIvPjwvc3ZnPg%3D%3D&amp;logoColor=white" alt="CLI 和 MCP 接入" /></a>
  <a href="https://flowllm-ai.github.io/AxonX/zh/docs"><img src="https://img.shields.io/badge/docs-AxonX-blue?style=flat-square&amp;logo=readthedocs&amp;logoColor=white" alt="AxonX 中文文档" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/README.md"><img src="https://img.shields.io/badge/English-Read-yellow?style=flat-square&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English" /></a>
  <a href="https://github.com/FlowLLM-AI/AxonX/blob/main/README_ZH.md"><img src="https://img.shields.io/badge/%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-%E9%98%85%E8%AF%BB-orange?style=flat-square&amp;logo=googletranslate&amp;logoColor=white" alt="阅读简体中文" /></a>
  <a href="https://deepwiki.com/FlowLLM-AI/AxonX"><img src="https://img.shields.io/badge/DeepWiki-Ask_Devin-navy?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMyA0aDZsMyAyIDMtMmg2djE2aC02bC0zIDItMy0ySDN6IE0xMiA2djE2Ii8%2BPC9zdmc%2B&amp;logoColor=white" alt="通过 DeepWiki 了解 AxonX" /></a>
</p>

## AxonX 是什么？

**AxonX 是面向金融量化研究的 Agent-native Harness。**
它将数据处理、因子分析、训练、预测和回测抽象为输入输出明确的 **Task**，并通过插件系统管理不同量化方案。
Agent 可以通过 CLI / MCP 发现能力、查询任务协议、提交研究任务、跟踪执行并检查产物；研究者可以在 **AxonX Studio** 中完成对应操作，Studio 通过 HTTP / SSE 访问相同的 Job 接口，与 CLI / MCP 共享任务、工作区和执行结果。
AxonX 提供研究执行环境：插件定义算法，框架管理任务生命周期、日志、产物与上下游关系，让 Agent 和人类围绕同一份研究记录协作。

## 为什么使用 AxonX？

- **将研究代码复用为 Task。** 类型化输入输出明确数据、模型和产物的要求；通过可查询的 Task 协议发现能力、检查参数并提交研究任务。→ [Task 契约](https://flowllm-ai.github.io/AxonX/zh/reference/task-contracts)
- **执行过程可检查、可管理。** 将 Task 提交到独立 worker 进程，跟踪状态、进度、日志和结果，并支持等待与取消执行。→ [任务管理](https://flowllm-ai.github.io/AxonX/zh/guides/task-management)
- **从结果追溯输入。** 工作区保存参数、产物和上游 Task ID，Task Graph 明确上下游关系，便于复用数据集、追溯研究链路和检查实验差异。→ [任务血缘](https://flowllm-ai.github.io/AxonX/zh/concepts/task-lineage)
- **CLI、AxonX Studio 和 Agent 共用工作流程。** 脚本与 Agent 通过 CLI / MCP 调用能力，研究者通过浏览器表单和图表操作；各入口共享同一套 Job 与 Task 契约、任务记录和研究产物。→ [AxonX Studio](https://flowllm-ai.github.io/AxonX/zh/getting-started/studio) · [Agent](https://flowllm-ai.github.io/AxonX/zh/agent/usage)
- **插件扩展与远程执行。** 将研究能力打包为插件，支持查询、检查、构建、安装和卸载；明确选择远程执行目标，在目标环境运行任务并检查资源、日志与结果。→ [插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management) · [远程机器](https://flowllm-ai.github.io/AxonX/zh/guides/remote-machines)

![AxonX 研究与执行总览](docs/figures/getting-started/overview.svg)

## 快速开始

要求 **Python 3.12+**，本地 Task 执行支持 **macOS 和 Linux**。

### 从 PyPI 安装

```bash
pip install "axonx[studio]"
```

包含 CLI、HTTP API、MCP 和预构建的 AxonX Studio。只使用核心能力时，可安装 `axonx`。研究插件单独安装。

### 从源码安装

构建 Studio 需要 Node.js 22.13+（22.x）、24.x 或 26+：

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git && cd AxonX
pip install -e .
(cd axonx_studio && npm ci && npm run build)
pip install ./axonx_studio
```

开发依赖和前端热更新见[贡献指南](CONTRIBUTING_ZH.md)与 [Studio 开发文档](https://flowllm-ai.github.io/AxonX/zh/development/studio)。

### 配置环境变量

在启动目录创建 `.env`，CLI 会自动加载当前目录或父目录中的配置；已有环境变量优先。

```dotenv
# 本机服务鉴权：替换为自己的 token
AXONX_SERVICE_TOKEN=replace-with-your-local-service-token

# Optional: target AxonX service (axonx start --config remote)
# AXONX_TARGET=192.0.2.10:1024
# AXONX_TARGET_TOKEN=your-target-service-token
```

其他环境变量配置见 [example.env](example.env)。

### 启动 AxonX

默认启动：

```bash
axonx start
```

指定监听 IP 和端口：

```bash
axonx start --service.host 127.0.0.1 --service.port 8181
```

使用远程配置启动：

```bash
axonx start --config remote
```

### AxonX Studio 能力

在 **Settings → Service token** 中填入 `AXONX_SERVICE_TOKEN`，即可在浏览器中：

- 查询 Task 定义、填写参数、提交任务，查看状态、进度、日志和上下游关系。
- 浏览工作区文件，检查参数、metadata 和研究产物。
- 查看因子分析、训练曲线、预测结果、回测指标与分期汇总。
- 查询机器资源，在已配置的本机与远程服务之间切换。
- 配置模型后，在 Agent 页面通过会话排查任务和分析研究结果。

<table>
  <tr>
    <th width="50%">首页</th>
    <th width="50%">任务管理</th>
  </tr>
  <tr>
    <td valign="top">
      <a href="docs/figures/studio/home.png"><img src="docs/figures/studio/home.png" alt="AxonX Studio 首页" width="100%" /></a>
    </td>
    <td valign="top">
      <a href="docs/figures/studio/task-list.png"><img src="docs/figures/studio/task-list.png" alt="AxonX Studio 任务管理：任务状态、进度与功能导航" width="100%" /></a>
    </td>
  </tr>
</table>

[Studio 入门](https://flowllm-ai.github.io/AxonX/zh/getting-started/studio)

## 5min Demo

以 [a158 插件](plugins/a158/README_ZH.md) 为例，体验插件管理、服务查询和量化研究任务。行情下载需在 `.env` 中配置 `AXONX_TUSHARE_TOKEN`，见 [example.env](example.env)。

### 插件命令

在服务使用的 Python 环境中安装，安装后重启服务：

```bash
pip install axonx-alpha158
axonx plugin list
axonx plugin show axonx-alpha158
```

### 非 Task 命令

查询服务版本、机器资源和工作区：

```bash
axonx version
axonx machine_status
axonx list_entries --path ''
```

### Task 命令

每一步成功后再提交下游；将占位 ID 替换为提交响应中的 `answer.task_id`。已有完整历史行情时跳过下载，因子分析可从 ETL 独立执行。

```bash
axonx get_task_definition --task a158_etl
axonx submit --task download_tushare_task --start-date 20140101 --end-date 20231231 --datasets 'static,stk_limit,daily,adj_factor,index_weight'
axonx submit --task a158_etl --start-date 20150101 --end-date 20231231
axonx submit --task a158_factor --source-tasks '<etl_task_id>'
axonx submit --task a158_train --source-tasks '<etl_task_id>' --train-start 20150101 --train-end 20230101
axonx submit --task a158_predict --source-tasks '<train_task_id>' --pred-start 20230101 --pred-end 20231231
axonx submit --task a158_backtest --source-tasks '<predict_task_id>'
axonx status --task-id '<backtest_task_id>'
axonx read_task_log --task-id '<backtest_task_id>'
axonx get_task_graph --task-id '<backtest_task_id>'
```

在 **AxonX Studio** 查看任务和研究结果。数据准备与完整流程见[研究流程](https://flowllm-ai.github.io/AxonX/zh/research/workflow)，更多命令见[开发与运维指南](docs/zh/dev_guide.md)。

## 为 Agent 提供 Harness 环境

| 方式 | 使用方法 | 开发指南 |
| --- | --- | --- |
| 内置 Agent | 配置模型后，运行 `axonx start --components.agent.default.load_dev_guide true`，在 **Studio → Agent** 中使用。 | 默认加载由 [docs/en/dev_guide.md](docs/en/dev_guide.md) 打包的指南；模型配置见 [example.env](example.env)。 |
| 外置 Agent | 为 Codex、Claude Code 等手动安装 [skills/axonx/SKILL.md](skills/axonx/SKILL.md)，通过 CLI / MCP 使用 AxonX。 | 一并提供 [docs/en/dev_guide.md](docs/en/dev_guide.md)，保留相对路径或调整 Skill 中的引用。 |

## Alpha158 与插件系统

[Alpha158](plugins/a158/README_ZH.md) 将 158 个价量特征、LightGBM 模型和 TopN 回测封装为研究 Task。插件定义算法，框架管理执行与产物；主链路为 **ETL → Train → Predict → Backtest**，因子分析从 ETL 独立分支执行。运行前准备好工作区中的 Tushare 历史数据，每一步成功后再提交下游，占位 ID 替换为实际返回的 `answer.task_id`。完整参数与数据要求见插件文档，扩展与远程部署见[插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management)。

| 操作 | 命令 | 说明 / 产物 |
| --- | --- | --- |
| 安装插件 | `pip install axonx-alpha158` | 在执行服务的 Python 环境中安装，完成后启动或重启服务。 |
| 查看插件 | `axonx plugin list`<br>`axonx plugin show axonx-alpha158` | 检查安装状态、插件信息与注册的 Task。 |
| 查询 Task 协议 | `axonx get_task_definition --task a158_etl` | 查看输入输出定义和参数要求；其他阶段替换 Task 注册名。 |
| 数据处理 | `axonx submit --task a158_etl --start-date 20150101` | 从工作区行情生成特征、标签、交易状态与统计。 |
| 因子分析 | `axonx submit --task a158_factor --source-tasks '<etl_task_id>'` | 生成因子诊断结果；不作为训练的前置条件。 |
| 训练 | `axonx submit --task a158_train --source-tasks '<etl_task_id>'` | 生成 LightGBM 模型、验证曲线与特征重要性。 |
| 预测 | `axonx submit --task a158_predict --source-tasks '<train_task_id>'` | 生成样本外预测与统计。 |
| 回测 | `axonx submit --task a158_backtest --source-tasks '<predict_task_id>'` | 生成 TopN 回测、分期汇总与持仓产物。 |
| 检查插件源码 | `axonx plugin inspect ./plugins/a158` | 从仓库根目录检查插件元数据，不安装。 |
| 构建插件 | `axonx plugin build ./plugins/a158` | 从源码生成或复用缓存 wheel。 |
| 从源码安装 | `axonx plugin install ./plugins/a158` | 安装插件；按响应中的 `restart_required` 重启服务。 |
| 卸载插件 | `axonx plugin uninstall axonx-alpha158` | 卸载指定插件；按响应要求重启服务。 |

## Benchmark：Agent 开发市场横截面增强特征

同一个因子在不同市场环境下，可能具有不同的预测作用。例如，个股下跌在普跌环境与市场上涨环境中含义不同；趋势、放量和相对表现也需要结合市场横截面解释。

这个案例中，Codex 按[开发与运维指南](docs/en/dev_guide.md)开发了独立插件 [Alpha158 Enhanced](plugins/a158_enhanced/README_ZH.md)，并通过 AxonX 管理训练、预测与回测实验。增强版保留原始 158 个特征，增加 26 个环境与交互特征，共 **184 个特征**；注册 `a158e_etl`、`a158e_factor`、`a158e_train`、`a158e_predict`、`a158e_backtest` 五个 Task。

| 特征组        | 新增数量 | 内容                                                             |
| ------------- | -------: | ---------------------------------------------------------------- |
| `market`      |       11 | 市场收益分布、上涨比例、涨跌停比例、趋势、冲击、放量与金额集中度 |
| `liquidity`   |        6 | 历史成交金额排名、个股放量、金额分组收益与组间价差               |
| `relative`    |        5 | 个股相对市场 / 金额组收益、横截面排名与相对趋势                  |
| `interaction` |        4 | 市场冲击、下跌、组间价差及市场放量与个股特征的交互               |

成交金额分组反映交易活跃度，不等同于市值分组。历史金额分组使用截至 T−1 的信息，当日环境特征在信号日收盘后可用。

### 实验设置与全局信号指标

训练期为 **2015–2022 年**，在 **2023–2024 年**比较基线、市场组、市场＋流动性＋相对组、全部四组，并按预设规则锁定全部四组。最终确认期为 **2025-01-01 至 2026-09-30**，只比较基线和锁定方案。原始数据已逐值对照，训练配置保持一致，随机种子为 42，交易成本率为 0.002，年化使用 252 个交易日。

| 区间             | 方案              | 特征数 | RankIC | 年化 RankICIR |
| ---------------- | ----------------- | -----: | -----: | ------------: |
| 筛选期 2023–2024 | Alpha158 基线     |    158 | 0.0876 |       11.3374 |
| 筛选期 2023–2024 | Enhanced 全部四组 |    184 | 0.0974 |       11.0976 |
| 确认期 2025–2026 | Alpha158 基线     |    158 | 0.0915 |       12.6313 |
| 确认期 2025–2026 | Enhanced 全部四组 |    184 | 0.0967 |       11.9480 |

RankIC 衡量每日全横截面预测排序与收益排序的相关性；年化 RankICIR 为日 RankIC 均值 / 标准差 × √252。确认期 RankIC 提升约 **0.0052**，RankICIR 下降。

### 确认期 Top10 / Top20 / Top30 头部组合

| 组合  | 基线净年化收益 | 增强净年化收益 | 基线净 Sharpe | 增强净 Sharpe | 基线最大回撤 | 增强最大回撤 |
| ----- | -------------: | -------------: | ------------: | ------------: | -----------: | -----------: |
| Top10 |         −5.74% |         28.21% |       −0.0631 |        0.9430 |      −39.48% |      −31.53% |
| Top20 |         −3.24% |         24.93% |       −0.0058 |        0.9040 |      −38.43% |      −31.08% |
| Top30 |          2.13% |         19.10% |             — |             — |      −38.21% |      −30.44% |

Top10 / Top20 / Top30 净年化收益分别提升 **33.95 / 28.16 / 16.97 个百分点**。净 Sharpe 使用扣费后日收益减日无风险收益计算。已提交的实验材料未列出 Top30 净 Sharpe，也未列出各组合 Information Ratio，因此此处不补填推算值。

不同指标的口径需要区分：

| 指标              | 衡量对象                   | 当前回测 / 实验口径                                                            |
| ----------------- | -------------------------- | ------------------------------------------------------------------------------ |
| RankICIR          | 全横截面信号相关性的稳定性 | 日 RankIC 均值 / 标准差，年化                                                  |
| 净 Sharpe         | 组合相对无风险收益的表现   | 本实验从扣费日收益计算；原始回测另有 `gross_sharpe`                            |
| Information Ratio | 组合相对指定基准的主动收益 | 原始回测以毛收益减基准日收益计算并年化；包括 `universe` 和数据中可用的指数基准 |

读取完整回测汇总时，应按 `top{N}_information_ratio_{基准}` 分别比较同一基准，不能用 RankICIR 或净 Sharpe 代替组合 IR。[回测解读](https://flowllm-ai.github.io/AxonX/zh/research/backtest)说明收益、成本与交易假设。

本次确认期 Top1–3 收益下降，RankIC、Top10/20 日配对增量的 95% 区块 bootstrap 区间均跨零。因此，上表展示该数据快照上的正向点估计，尚不足以证明稳定增量。回测使用收盘成交代理、延迟退出和未结清持仓按成本记账，未模拟盘后排队和部分成交。

![AxonX Studio 回测整体指标](docs/figures/studio/backtest-overall.png)

截图展示结果页面的能力；具体 benchmark 数值以上表及实验材料为准。

| 实验材料                                                | 内容                                         |
| ------------------------------------------------------- | -------------------------------------------- |
| [实验计划](plugins/a158_enhanced/DEVELOPMENT_PLAN.md)   | 特征时点、控制变量、筛选与确认规则           |
| [实验过程](plugins/a158_enhanced/EXPERIMENT_PROCESS.md) | 开发、验证、执行记录与方案锁定               |
| [实验结果](plugins/a158_enhanced/EXPERIMENT_RESULTS.md) | 消融、全部 TopN、分年 / 环境表现与统计区间   |
| [材料索引](plugins/a158_enhanced/experiments/README.md) | 随仓库提交的指标、数据一致性与特征覆盖率汇总 |

## AxonX CLI 命令与远程执行

CLI 的服务命令调用相应 Job；`exec` 和未指定目标的插件管理命令在当前 Python 环境执行。

| 用途                 | 命令示例                                                                                      |
| -------------------- | --------------------------------------------------------------------------------------------- |
| 帮助 / 服务版本      | `axonx help` / `axonx version`                                                                |
| 启动服务             | `axonx start`                                                                                 |
| 查看注册 Task        | `axonx exec` / `axonx list_installed_task_definitions`                                        |
| 查询 Task 协议       | `axonx get_task_definition --task a158_etl`                                                   |
| 当前进程执行         | `axonx exec --task demo --x 2 --y 3`                                                          |
| 提交研究任务         | `axonx submit --task a158_train --source-tasks '<etl_task_id>'`                               |
| 等待本次运行         | `axonx wait_task --task-id '<task_id>' --run-id '<run_id>' --client-timeout 86400`            |
| 跟踪进度和日志       | `axonx stream_task --task-id '<task_id>' --stream true`                                       |
| 查询任务列表 / 状态  | `axonx list_task_statuses` / `axonx status --task-id '<task_id>'`                             |
| 读取日志             | `axonx read_task_log --task-id '<task_id>'`                                                   |
| 查询上下文 / 依赖图  | `axonx get_task_context --task-id '<task_id>'` / `axonx get_task_graph --task-id '<task_id>'` |
| 取消任务             | `axonx cancel --task-id '<task_id>'`                                                          |
| 删除已结束任务及文件 | `axonx delete_tasks --task-ids '["<task_id>"]'`                                               |
| 浏览工作区           | `axonx list_entries --path ''`                                                                |
| 预览产物             | `axonx preview_file --path '<工作区相对路径>'`                                                |
| 查询机器 / 资源      | `axonx list_machines` / `axonx machine_status`                                                |
| 查询插件 / 详情      | `axonx plugin list` / `axonx plugin show axonx-alpha158`                                      |
| 检查 / 构建插件源码  | `axonx plugin inspect ./plugins/a158` / `axonx plugin build ./plugins/a158`                   |
| 安装 / 卸载插件      | `axonx plugin install ./plugins/a158` / `axonx plugin uninstall axonx-alpha158`               |

### CLI 直连远程服务

目标机器先安装 AxonX 与研究插件，配置自己的 `AXONX_SERVICE_TOKEN` 并启动可达的服务。客户端配置目标 token，在支持远程的命令上明确指定地址：

```bash
export AXONX_TARGET_TOKEN='your-target-service-token'
axonx machine_status --target 192.0.2.10:1024
axonx plugin list --target 192.0.2.10:1024
axonx submit --task demo --x 2 --y 3 --target 192.0.2.10:1024
axonx wait_task --task-id '<task_id>' --run-id '<run_id>' \
  --client-timeout 120 --target 192.0.2.10:1024
```

地址为示例，请替换为实际服务。提交、等待、状态、日志和产物查询使用同一 `--target`；任务使用目标机器的插件、数据与工作区。CLI 直连无需启动本机服务。

远程插件安装会在本机构建 wheel，上传并安装到目标环境：

```bash
axonx plugin install ./plugins/a158 --target 192.0.2.10:1024
```

`plugin build` 始终在本机执行；远程 `plugin inspect` 接受目标已安装的 distribution / 插件名。`start` 和 `exec` 不通过 `--target` 远程执行。

### 在 Studio 中使用远程机器

在本机 `.env` 设置 `AXONX_TARGET` 和 `AXONX_TARGET_TOKEN`，然后启动仓库提供的注册配置：

```bash
axonx start --config remote
```

`remote` 继承默认配置，将目标地址与 token 加入服务的 `targets`。Studio 使用本机 token 访问同源后端，由后端转发到选中的远程服务。配置多个目标、自定义 YAML 和连接排查见[远程机器指南](https://flowllm-ai.github.io/AxonX/zh/guides/remote-machines)。

## AxonX 文档

| 主题                 | GitHub Pages 文档                                                                                                                                                                                                                |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 安装与首个 Task      | [快速开始](https://flowllm-ai.github.io/AxonX/zh/getting-started/quickstart)                                                                                                                                                     |
| 浏览器操作           | [AxonX Studio](https://flowllm-ai.github.io/AxonX/zh/getting-started/studio)                                                                                                                                                     |
| Component、Job、Task | [架构](https://flowllm-ai.github.io/AxonX/zh/concepts/architecture) · [框架扩展](https://flowllm-ai.github.io/AxonX/zh/development/framework-extensions)                                                                         |
| Task 协议与生命周期  | [Task 契约](https://flowllm-ai.github.io/AxonX/zh/reference/task-contracts) · [任务管理](https://flowllm-ai.github.io/AxonX/zh/guides/task-management) · [任务血缘](https://flowllm-ai.github.io/AxonX/zh/concepts/task-lineage) |
| Agent 开发与运维     | [开发指南](https://flowllm-ai.github.io/AxonX/zh/dev_guide) · [Agent 配置](https://flowllm-ai.github.io/AxonX/zh/agent/configuration) · [MCP 集成](https://flowllm-ai.github.io/AxonX/zh/agent/mcp-integration)                  |
| 插件开发与部署       | [插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management) · [Alpha158](https://flowllm-ai.github.io/AxonX/zh/plugins/alpha158) · [Alpha158 Enhanced](https://flowllm-ai.github.io/AxonX/zh/plugins/alpha158-enhanced) |
| 量化研究             | [研究流程](https://flowllm-ai.github.io/AxonX/zh/research/workflow) · [结果解读](https://flowllm-ai.github.io/AxonX/zh/research/results) · [回测解读](https://flowllm-ai.github.io/AxonX/zh/research/backtest)                   |
| 远程运行             | [远程机器](https://flowllm-ai.github.io/AxonX/zh/guides/remote-machines)                                                                                                                                                         |
| CLI 与配置           | [CLI](https://flowllm-ai.github.io/AxonX/zh/reference/cli) · [配置](https://flowllm-ai.github.io/AxonX/zh/reference/configuration)                                                                                               |

浏览[完整中文文档](https://flowllm-ai.github.io/AxonX/zh/docs)或[英文文档](https://flowllm-ai.github.io/AxonX/en/docs)。

## Contributing

欢迎提交问题反馈、功能建议、文档改进、研究插件和代码贡献。请先搜索[已有 Issues](https://github.com/FlowLLM-AI/AxonX/issues)，开发环境、目录约定和检查要求见[贡献指南](CONTRIBUTING_ZH.md)。

研究算法放在 `plugins/`，复用框架扩展点；行为变化同步更新中英文文档。贡献实验时，请附数据与时间窗口、参数、成本口径和可复核的结果材料。

## License

AxonX 基于 [Apache License 2.0](LICENSE) 开源。
