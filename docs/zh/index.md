# AxonX 文档导航

AxonX 是面向金融量化研究的 Agent Harness。插件提供算法，Task 定义研究步骤的输入与输出，框架管理执行、记录和产物。研究人员、外部 Agent 与脚本通过 Studio、CLI 或 MCP 使用同一套 Job 与工作区记录。

## 选择你的起点

| 目标                | 从哪里开始                                                                           | 完成后你能做什么                     |
| ------------------- | ------------------------------------------------------------------------------------ | ------------------------------------ |
| 第一次使用 AxonX    | [快速开始](getting-started/quickstart.md) → [Studio 入门](getting-started/studio.md) | 提交 demo、等待终态、检查参数与结果  |
| 开展量化研究        | [研究总览](research/overview.md) → [研究流程](research/workflow.md)                  | 准备数据，串联 ETL、训练、预测和回测 |
| 让外部 Agent 做研究 | [Agent 接入总览](agent/overview.md) → [外部 Agent](agent/external.md)                | 通过 Skill、CLI 或 MCP 操作研究服务  |
| 在 Studio 中对话    | [内置 Agent 配置](agent/configuration.md) → [内置 Agent 使用](agent/usage.md)        | 查询任务、排障、解释已有研究证据     |
| 部署或管理任务      | [运行总览](guides/overview.md) → [远程机器](guides/remote-machines.md)               | 跟踪执行、管理文件、连接目标服务     |
| 编写插件或接入代码  | [开发总览](development/overview.md) → [Task 契约](reference/task-contracts.md)       | 实现研究 Task，注册插件，调用服务    |

先了解项目定位和实验案例，可读[项目概览](../../README_ZH.md)。内置 demo 不需要行情或模型凭据；研究插件需要数据，内置 Agent 需要模型配置，外部 Agent 使用自身宿主的模型配置。

## 文档如何组织

### 开始使用：建立最小闭环

从[快速开始](getting-started/quickstart.md)完成一次真实执行，再用 [Studio](getting-started/studio.md)查看同一工作区。随后阅读[架构](concepts/architecture.md)、[Job 与 Task](concepts/jobs-and-tasks.md)、[任务生命周期](concepts/task-lifecycle.md)、[任务血缘](concepts/task-lineage.md)和[工作区](concepts/workspace.md)，理解提交、执行与持久记录之间的关系。

### 量化研究：从数据到可检查的结论

先从[研究总览](research/overview.md)选择目标。[研究流程](research/workflow.md)和 [Tushare 数据](research/tushare.md)负责数据准备与阶段执行；[结果解读](research/results.md)负责检查各阶段产物；[实验设计与确认](research/experiments.md)、[回测口径](research/backtest.md)和[策略比较](research/strategy-comparison.md)负责评估证据。

[插件管理](plugins/management.md)说明安装、发现和部署。[Alpha158](../../plugins/qlib_a158/README_ZH.md)是基础研究链，[Qlib Factor](../../plugins/qlib_factor/README_ZH.md)提供增强特征与消融案例；[Qlib Strategy](../../plugins/qlib_strategy/README_ZH.md)增加排名保留和有限换仓。算法参数与实验数值以插件文档为准。

### Agent：选择外部宿主或内置会话

[接入总览](agent/overview.md)说明两条路径的前置条件。[外部 Agent](agent/external.md)介绍 Skill 与 CLI 的研究操作，[MCP 接入](agent/mcp-integration.md)解释服务工具发现与响应；[内置配置](agent/configuration.md)和[内置使用](agent/usage.md)介绍 Studio 中的 Claude Agent SDK 会话。

### 运行与部署：维护服务和执行环境

[运行总览](guides/overview.md)串联服务准备与记录维护。日常操作包括[任务管理](guides/task-management.md)、[文件浏览](guides/workspace-files.md)和[任务快照同步](guides/task-sync.md)。部署先阅读[鉴权](guides/authentication.md)、[服务托管](guides/deployment.md)与[远程机器](guides/remote-machines.md)，按需设置 [HTTP 代理](guides/http-proxy.md)、[定时 Job](guides/scheduling.md)及[钉钉通知](research/notifications.md)。故障、备份和恢复见[运维指南](guides/operations.md)。

### 接口参考：查参数和响应

先在[参考总览](reference/overview.md)选择接口。命令语法见 [CLI](reference/cli.md)，程序调用见 [Python](reference/python.md)，连接与启动字段见[客户端配置](reference/client-configuration.md)和[服务端配置](reference/configuration.md)。

HTTP 协议从 [API 总览](api/overview.md)开始，按需查询[任务](api/tasks.md)、[事件](api/events.md)、[文件](api/workspace.md)、[机器](api/machines.md)、[插件与同步](api/plugins-sync.md)和 [Agent 会话](api/agent.md)。

### 开发扩展：实现能力并保持契约

先在[开发总览](development/overview.md)选择扩展层。[贡献指南](../../CONTRIBUTING_ZH.md)负责开发环境与检查要求，[开发与运行指南](dev_guide.md)负责 Task 开发和 CLI 实践，[框架扩展](development/framework-extensions.md)与 [Studio 开发](development/studio.md)负责各自扩展点。实现时查阅 [Task 契约](reference/task-contracts.md)、[插件协议](reference/plugin-manifest.md)和[研究产物协议](reference/research-artifacts.md)。

## 阅读约定

操作指南围绕具体目标组织；参考页给出字段、响应与边界；项目和插件 README 分别维护项目概览与算法说明。中英文使用相同页面路径，截图和图示共用英文资源。

示例凭据、地址和 Task ID 需要替换为实际值。以所连服务发现的 Job 与 Task Schema 为准；提交成功后仍需等待 Task 终态。同名重跑会替换已结束任务的目录，实验比较应保留不同身份的记录。

遇到问题先查[常见问题](faq.md)，再按[运维指南](guides/operations.md)定位服务、Job 或 Task 层的故障。
