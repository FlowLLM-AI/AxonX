---
title: Claude Agent 配置
description: 区分框架字段、Claude SDK 选项、会话存储与工具权限。
---

# Claude Agent 配置

当前内置 Agent 后端是 `claude`，由 Claude Agent SDK 实现。AxonX 管理会话身份、Job 工具桥接和状态目录；SDK 管理模型调用及自身执行选项。

![配置层次](../../figures/agent/configuration-layers.svg)

## 基础配置

自定义服务配置继承 `default`，覆盖 Agent 组件即可：

```yaml
extends: default
components:
  agent:
    default:
      backend: claude
      setting_sources: [project]
      state_dir: agent/claude
      session_store:
        backend: local
        path: agent/session-store
      job_tools:
        - list_entries
        - preview_file
        - list_task_ids
        - list_task_statuses
        - status
        - read_task_log
        - get_task_graph
        - get_task_context
```

此配置展示字段结构；模型与权限设置继续继承默认值。服务启动时会校验 Job 名称是否已配置，名单不能为空字符串、不允许重复；字符串不能代替列表。

## 模型环境

默认配置把服务环境中的变量映射到 SDK 子进程：

| 服务环境变量 | SDK 环境用途 |
| --- | --- |
| `CLAUDE_CODE_API_KEY` | `ANTHROPIC_AUTH_TOKEN` |
| `CLAUDE_CODE_BASE_URL` | `ANTHROPIC_BASE_URL` |
| `CLAUDE_CODE_MODEL_NAME` | `ANTHROPIC_MODEL` 及默认模型别名 |

```bash
export CLAUDE_CODE_API_KEY='<模型凭据>'
export CLAUDE_CODE_BASE_URL='<兼容后端地址>'
export CLAUDE_CODE_MODEL_NAME='<可用模型名>'
```

配置的具体地址与模型名由可用后端决定。AxonX 当前没有内置“选择任意模型后端”的适配目录，不应把一个 env 映射解释为所有服务兼容。

`components.agent.default.env` 是 SDK 子进程环境覆盖，框架会合并 Application 环境与该映射。不要把模型密钥放入会话提示或文件预览示例。

## 框架管理字段

| 字段 | 默认行为 | 说明 |
| --- | --- | --- |
| `backend` | 默认配置 `claude` | 当前内置实现 |
| `job_tools` | 组件构造默认空列表，默认配置给出八个查询 Job | 进程内 AxonX MCP 工具名单 |
| `state_dir` | `agent/claude` | 用于 SDK 配置目录，按组件名称再分一层 |
| `session_store.backend` | `local` | 当前仅支持 local |
| `session_store.path` | `agent/session-store` | 会话存储根目录 |
| `cwd` | 工作区根目录 | SDK 选项，由框架解析执行目录 |

状态路径相对工作区解析，绝对状态路径也必须位于工作区内。默认组件名为 `default` 时，SDK 配置目录是 `<workspace>/agent/claude/default`。

`cwd` 为空时使用工作区；相对 `cwd` 必须在工作区内，绝对 `cwd` 可指向其他目录。这会改变项目设置发现及会话项目身份，应先明确执行范围。

如果子进程环境显式设置 `CLAUDE_CONFIG_DIR`，框架不会再生成默认配置目录。会话 `session_store.path` 与 SDK 配置目录是不同用途，不要混为同一个缓存。

## SDK 选项与权限

组件剩余关键字必须是当前安装 SDK 的 `ClaudeAgentOptions` 字段；未知选项会在构造时失败。字段随 SDK 版本可能变化，以实际依赖版本与运行校验为准。

默认配置包含 `permission_mode: bypassPermissions`、`setting_sources: [project]`、`session_store_flush: batched` 以及 Claude Code preset system prompt。默认追加提示要求以 AxonX 身份回答，并先查询实际工作区证据。

`setting_sources: [project]` 只声明加载项目级 Claude 设置，不意味着 SDK 自身工具被禁用。可选 skills 与 local plugins 属于 SDK 选项，默认配置中只是注释示例：

```yaml
# 以下为 SDK 配置示例，具体值需匹配安装的 SDK
components:
  agent:
    default:
      skills: all
      plugins:
        - type: local
          path: /path/to/skills-plugin
```

路径示例需替换成服务机器上的实际插件位置。修改 SDK 权限模式或工具限制时使用该版本明确支持的值，并验证项目设置的影响。

## Job 工具暴露

AxonX 把名单中的 Job 映射为 `mcp__axonx__<job-name>`，追加到 SDK `allowed_tools`；名单外 Job 不经这条桥接暴露。已有 `mcp_servers` 不能占用保留名 `axonx`。

默认八个 Job 用于任务和文件查询，但 `allowed_tools` 的桥接名单不等于 SDK 整体安全策略。SDK 自身文件、命令工具及 project/plugins 可能具备其他能力，尤其默认 `bypassPermissions` 不会把所有动作变成只读。

如果增加 `submit` 或 `cancel`，会改变 Agent 可调用的工作区操作。配置名单是能力授权，需要结合服务账号权限、cwd、SDK 工具和项目设置一起审查实际效果。

## 会话字段由框架管理

不能在组件 SDK 选项中手工配置 `resume`、`session_id`、`continue_conversation` 或 `session_store` 来取代 AxonX 会话管理。后端为新会话生成 UUID，续接通过请求中的 `session_id`，并始终使用框架会话存储。

每个 session_id 有独立轮次锁；同一会话的执行串行。运行中删除会话被拒绝，停止轮次调用 SDK interrupt，不等同于取消研究 Task。

## 调用深度

默认 `agent_chat` Step 的 `max_depth` 为 3，用于限制经过桥接的嵌套 Agent 调用链。当前深度达到限制时返回失败，不再调用模型。

```yaml
jobs:
  agent_chat:
    steps:
      - backend: agent_stream
        max_depth: 3
```

这不是用户会话最多三次提问，也不是最多三次工具调用。内部深度参数由框架注入，不应作为普通用户参数手动维护。

## 应用与验证

配置更新后重启服务，先确认 Agent 组件能启动、Job 目录存在，再进行一个只查询已有任务的短轮次。检查实际工具块和最终结果，核对模型连接、cwd 和会话存储。

本页依据仓库的默认配置和适配层，没有发起实际模型请求。SDK 的外部能力和模型可用性需要在部署环境单独验证。

## 相关文档与实现

- [Agent 使用](usage.md)、[鉴权](../guides/authentication.md)
- [`默认配置`](../../../axonx/config/default.yaml)
- [`Claude backend`](../../../axonx/components/agent/claude/backend.py)
- [`Job 工具桥接`](../../../axonx/components/agent/claude/tools.py)
