---
title: Agent 接入总览
description: 选择外部 Agent 的 CLI / MCP 接入，或 Studio 中的内置 Agent 会话。
---

# Agent 接入总览

AxonX 为 Agent 提供可发现的 Task 契约、执行接口和研究记录。你可以让已有 Agent 宿主操作 AxonX，也可以在 Studio 中使用内置会话。两条路径共享研究服务与工作区，模型配置和会话管理由不同一方负责。

![相互独立的 Agent 接入路径](../../figures/agent/mcp-surfaces.svg)

## 选择路径

|            | 外部 Agent                                                 | 内置 Agent                                          |
| ---------- | ---------------------------------------------------------- | --------------------------------------------------- |
| 入口       | Codex、Claude Code 等宿主                                  | Studio → Agent，或 `agent_chat` Job                 |
| 模型配置   | 外部宿主负责                                               | 服务端 Claude Agent SDK 配置                        |
| AxonX 连接 | CLI 直连或服务 `/mcp`                                      | 内置组件通过 Dispatcher 调用配置的 Job              |
| 操作说明   | [AxonX Skill](../../../skills/axonx/SKILL.md)与开发指南    | 可按需加载随包分发的开发指南                        |
| 工具范围   | CLI 可用命令或服务公开 MCP 目录                            | `job_tools` 与 SDK 自身工具、权限设置               |
| 会话记录   | 外部宿主管理                                               | AxonX 会话存储管理                                  |
| 推荐阅读   | [外部 Agent](external.md) → [MCP 接入](mcp-integration.md) | [内置配置](configuration.md) → [内置使用](usage.md) |

外部 Agent 接入不要求配置 `CLAUDE_CODE_*` 或开启内置开发指南。内置 Agent 的默认八个 Job 工具用于任务与文件查询；外部 MCP 公开目录可能包含提交、取消和安装等更多操作。实际能力以所用路径的配置与 Schema 为准。

## 共同的研究循环

1. 确定服务地址、凭据与工作区，查询机器资源和已安装插件。
2. 发现 Task 定义，读取真实输入输出 Schema。
3. 复用成功上游，只执行本次实验需要的阶段。
4. 保存提交返回的 `task_id` 和 `run_id`，等待该次执行终态。
5. 检查日志、metadata、产物与血缘，再形成研究结论。

通过 CLI 直连时，各阶段持续使用同一 `--target`；在 Studio 中选择机器时，请求经同源后端转发。任务、数据和插件位于执行服务的环境，接入 Agent 不会自动迁移它们。

## 按目标继续

- 操作服务或开发研究插件：[外部 Agent](external.md)、[开发与运行指南](../dev_guide.md)。
- 在浏览器分析已有记录：[内置 Agent 使用](usage.md)。
- 设计消融和独立确认：[实验设计与确认](../research/experiments.md)。
- 查连接、返回值与事件：[MCP 接入](mcp-integration.md)、[API 总览](../api/overview.md)。
