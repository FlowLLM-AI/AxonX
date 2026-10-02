# AxonX 中文文档

AxonX 将量化研究能力封装为插件，通过 Task 运行计算，通过 Job、CLI、Studio 与 MCP 提供统一入口。

![AxonX Studio overview](../figures/studio/home.png)

## 从这里开始

| 目标         | 阅读路径                                                                                                                      |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| 首次体验     | [项目介绍](getting-started/introduction.md) → [快速开始](getting-started/quickstart.md) → [Studio](getting-started/studio.md) |
| 开展量化研究 | [研究流程](research/workflow.md) → [结果解读](research/results.md) → [回测](research/backtest.md)                             |
| 调用服务     | [API 总览](api/overview.md) → [Task API](api/tasks.md) → [CLI](reference/cli.md) / [Python](reference/python.md)              |
| 接入 Agent   | [Agent 配置](agent/configuration.md) → [使用](agent/usage.md) / [MCP 接入](agent/mcp-integration.md)                          |
| 扩展项目     | [开发指南](dev_guide.md) → [插件协议](reference/plugin-manifest.md) → [框架扩展](development/framework-extensions.md)         |

内置 demo 不需要外部数据或模型凭据。研究插件、远程机器、Agent 和同步功能各自有配置前置条件，请按对应指南准备。

## 文档目录

### 入门

- [AxonX 项目介绍](getting-started/introduction.md)
- [快速开始](getting-started/quickstart.md)
- [Studio 入门](getting-started/studio.md)

### 核心概念

- [架构概述](concepts/architecture.md)
- [Job 与 Task](concepts/jobs-and-tasks.md)
- [任务身份与生命周期](concepts/task-lifecycle.md)
- [任务依赖与血缘](concepts/task-lineage.md)
- [工作区与持久记录](concepts/workspace.md)

### 操作与部署

- [鉴权与权限边界](guides/authentication.md)
- [服务部署与 Studio 托管](guides/deployment.md)
- [HTTP 上游代理](guides/http-proxy.md)
- [日志排障与备份恢复](guides/operations.md)
- [插件安装与部署](guides/plugin-management.md)
- [远程机器使用](guides/remote-machines.md)
- [定时 Job 调度](guides/scheduling.md)
- [任务提交与管理](guides/task-management.md)
- [任务快照同步](guides/task-sync.md)
- [工作区浏览与预览](guides/workspace-files.md)

### 量化研究

- [回测结果解读](research/backtest.md)
- [钉钉通知](research/notifications.md)
- [研究结果解读](research/results.md)
- [策略比较](research/strategy-comparison.md)
- [Tushare 数据下载](research/tushare.md)
- [量化研究流程](research/workflow.md)

### Agent

- [Claude Agent 配置](agent/configuration.md)
- [外部 Agent 的 MCP 接入](agent/mcp-integration.md)
- [Agent 使用](agent/usage.md)

### API 与事件

- [Agent API](api/agent.md)
- [SSE 事件协议](api/events.md)
- [机器 API](api/machines.md)
- [API 协议总览](api/overview.md)
- [插件与同步 API](api/plugins-sync.md)
- [任务 API](api/tasks.md)
- [工作区与文件传输 API](api/workspace.md)

### 配置与协议参考

- [CLI 参考](reference/cli.md)
- [客户端与连接配置](reference/client-configuration.md)
- [服务端配置参考](reference/configuration.md)
- [插件包与贡献协议](reference/plugin-manifest.md)
- [Python 调用参考](reference/python.md)
- [研究产物与 Studio 展示协议](reference/research-artifacts.md)
- [Task 输入输出与持久化协议](reference/task-contracts.md)

### 开发与扩展

- [框架扩展](development/framework-extensions.md)
- [扩展 Studio](development/studio.md)

### 其他入口

- [开发指南](dev_guide.md)：Task 开发流程与实践。
- [常见问题](faq.md)：连接、任务、产物、插件与 Agent 问题。

## 阅读约定

正文使用中文，截图与 SVG 使用英文。文中示例凭据和标识为占位值；截图仅保留无隐私的演示区域。

参数、默认值与返回结构以当前源码为依据，具体安装的 Task 以任务定义目录为准。遇到问题从 [排障与恢复](guides/operations.md) 开始。
