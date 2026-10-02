# AxonX 项目介绍

AxonX 是面向金融量化研究的 Harness 框架。它把数据处理、因子分析、训练、预测和回测承载为有输入输出契约的 Task，通过 Job 接口连接 CLI、Studio 与 Agent，让研究代码、任务运行、日志和产物能在同一个工作区中追踪。

![AxonX research and execution overview](../../figures/getting-started/overview.svg)

## 从你的工作开始

| 我想做什么 | 阅读入口 |
| --- | --- |
| 安装并运行第一个任务 | [快速开始](quickstart.md) |
| 在浏览器提交任务、看日志与结果 | [Studio 入门](studio.md) |
| 完成数据到回测的研究链 | [量化研究流程](../research/workflow.md) |
| 将任务放到另一台机器执行 | [远程机器使用](../guides/remote-machines.md) |
| 让 Agent 读取任务、产物与上下文 | [Agent 研究助手](../agent/usage.md) |
| 从自己的程序调用能力 | [API 总览](../api/overview.md)、[Python 调用](../reference/python.md) |
| 编写自己的研究任务 | [已有开发与运行指南](../dev_guide.md)、[插件协议](../reference/plugin-manifest.md) |

## 研究过程由什么组成

| 阶段 | 典型输入 | 典型结果 |
| --- | --- | --- |
| 原始数据 | Tushare 日期范围与数据集选择 | 工作区中的行情和基础数据 Parquet |
| ETL | 原始数据目录 | 特征、标签和可供后续阶段复用的数据集 |
| Analysis | ETL Task ID | 因子评分、分析结果文件 |
| Train | ETL Task ID 和模型配置 | 模型、指标和可选训练曲线 |
| Predict | Train Task ID | 离线预测数据与统计 |
| Backtest | Predict Task ID 和策略假设 | 日频回测、汇总与持仓相关产物 |

核心框架提供基础 Task 契约，具体因子、模型和回测逻辑由研究插件实现。上表描述典型研究链，实际输入以安装插件的 Task Schema 为准。Analysis 通常从 ETL 分支运行，不要求先于 Train 执行。

阶段间通过 `source_tasks` 记录上游 Task ID，结果保存在 Task 目录。你可以复用同一份 ETL 结果训练不同模型，或复用预测结果比较不同回测参数。框架保存关系供查询与展示；提交各阶段的动作由用户或调用程序组织。

## 三种使用入口

**CLI** 适合终端操作与脚本。`axonx exec` 在当前进程运行 Task；`axonx submit` 调用服务，将任务交给独立 worker。其他 Job 命令用于查询状态、日志、机器与工作区。

**Studio** 提供 Task Schema 表单、运行详情、机器资源、原始数据与研究结果页面。它向同源后端发送请求，远程机器选择由后端按配置转发。

**Agent** 可以调用配置中的 Job 工具查询任务、日志、文件和血缘，结合证据解释研究结果。内置 Agent 后端使用 Claude Agent SDK；外部 Agent 也可以通过同一服务的 MCP 接口调用 Job。

三种入口共用框架能力和工作区记录。它们的连接、鉴权和流式响应形式有区别，详见 [Job 与 Task](../concepts/jobs-and-tasks.md)、[鉴权](../guides/authentication.md)与 [MCP 接入](../agent/mcp-integration.md)。

## 能力分工

| 组成 | 负责的事情 |
| --- | --- |
| Application、Component、Job、异步 Step | 装配基础设施、校验调用参数并执行接口操作 |
| TaskManager、TaskRunner、同步 Task 步骤 | 启动 worker，执行计算并发布状态、进度、日志和结果 |
| 研究插件 | 实现数据处理、因子、模型、预测与回测算法 |
| 工作区 | 保存任务配置、元数据、事件与产物 |
| Studio | 根据公开接口与标准产物展示任务和研究结果 |
| Agent | 在配置允许的工具与 SDK 权限范围内协助研究和工程工作 |

进程隔离便于分开运行任务，但不是安全沙箱。机器资源页面提供监测，远程目标由调用方选择。收益定义、成本假设和交易约束需要核对具体插件；详见[回测解读](../research/backtest.md)。

## 下一步

第一次使用时，先用无需数据与模型凭据的 Demo 跑通[快速开始](quickstart.md)，确认提交、等待和结果读取，再安装研究插件。已经有服务的用户可直接阅读 [Studio 入门](studio.md) 或 [任务管理](../guides/task-management.md)。

实现结构见[架构概述](../concepts/architecture.md)；当前公开能力可通过服务的 `/jobs` 目录查询。
