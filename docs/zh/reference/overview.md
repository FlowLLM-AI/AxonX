# 参考手册

按需查询命令语法、配置字段、响应和事件。第一次执行请跟随[快速开始](../getting-started/quickstart.md)，完整研究链路见[研究流程](../research/workflow.md)。

## 选择接口

| 接口或设置                      | 参考                                     |
| ------------------------------- | ---------------------------------------- |
| 命令行与当前进程执行            | [CLI](cli.md)                            |
| 程序化服务调用                  | [Python](python.md)                      |
| 客户端地址、令牌与超时          | [客户端配置](client-configuration.md)    |
| 应用、Component 与 Job 装配     | [服务端配置](configuration.md)           |
| HTTP 发现与 JobResponse         | [API 总览](../api/overview.md)           |
| Task 提交、状态、上下文与关系图 | [Task API](../api/tasks.md)              |
| 实时进度与日志事件              | [SSE 事件](../api/events.md)             |
| 工作区列表与预览                | [工作区 API](../api/workspace.md)        |
| 机器与资源读数                  | [机器 API](../api/machines.md)           |
| 插件管理与快照同步              | [插件与同步 API](../api/plugins-sync.md) |
| 内置 Agent 会话                 | [Agent API](../api/agent.md)             |

外部 Agent 的服务工具发现见 [MCP 接入](../agent/mcp-integration.md)。MCP 暴露公共 Job；实时 SSE 使用 HTTP 事件端点。

## 分层理解响应

HTTP 传输状态、JobResponse 的 `success` 与 Task 终态分别回答不同问题。成功的 `submit` 返回 TaskHandle；使用其中的 `task_id` 与 `run_id` 等待本次执行，再检查最终状态。已安装插件与配置的 Job 决定实际能力，因此应在所连接服务上发现 Schema。

## 扩展契约

| 实现内容                        | 参考                                  |
| ------------------------------- | ------------------------------------- |
| Task 输入、输出、身份与生命周期 | [Task 契约](task-contracts.md)        |
| 插件打包、注册与发现            | [插件清单](plugin-manifest.md)        |
| 研究产物与 Studio 展示          | [研究产物契约](research-artifacts.md) |

研究插件开发步骤见[开发与运行指南](../dev_guide.md)，执行语义见 [Job 与 Task](../concepts/jobs-and-tasks.md)。
