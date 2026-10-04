---
title: 外部 Agent 的 MCP 接入
description: 通过 AxonX 服务 MCP 查询任务与工作区，并区分内置工具和 WebMCP。
---

# 外部 Agent 的 MCP 接入

AxonX HTTP 服务在 `/mcp` 提供 Streamable HTTP MCP，将公开 Job 映射为工具。外部 Agent 可以发现并调用实际服务目录中的工具，以任务状态、日志、血缘和文件构建研究证据。

MCP 是[外部 Agent](external.md)的一种接入方式。宿主可同时使用 [AxonX Skill](../../../skills/axonx/SKILL.md)提供研究操作说明；通过 CLI 操作服务时不必配置 MCP。内置会话使用另一条组件桥接路径，见[接入总览](overview.md)。

![相互独立的 Agent 接入路径](../../figures/agent/mcp-surfaces.svg)

## 连接信息

```text
URL:       http://127.0.0.1:1024/mcp
Transport: Streamable HTTP
Header:    Authorization: Bearer <AxonX 服务 token>
```

具体宿主配置格式各不相同，使用其受支持的远程 MCP 地址与 headers 配置。上面是连接参数，不是可直接复制到所有宿主的 JSON 配置。

当服务启用 token 时，MCP 同样要求 Bearer 鉴权。没有服务 token 时，默认需要鉴权的 Job 不进入公开目录；目录为空和连接被拒绝是不同问题，见[鉴权指南](../guides/authentication.md)。

## 先发现，再调用

工具目录来自当前运行的服务配置，可能包含查询、提交、取消、文件删除、shell 或插件安装等操作。外部 MCP 公开范围与内置 Agent 的 `job_tools` 名单不是同一层配置。

先调用 MCP `tools/list`，读取工具 Schema，再发起 `tools/call`。不要根据文档中的名称假定部署环境已经公开它。只把当前用户任务需要的能力提供给调用方。

## 用 AxonX Python MCP 客户端

项目已提供普通 JobResponse 的 MCP 客户端：

```python
import asyncio
import os
from axonx.components.client.mcp import McpClient

async def main():
    async with McpClient(
        target="http://127.0.0.1:1024",
        token=os.environ["AXONX_SERVICE_TOKEN"],
        timeout=60.0,
    ) as client:
        jobs = await client.list_jobs()
        names = {job.name for job in jobs}
        if "list_task_statuses" not in names:
            raise RuntimeError("服务未公开任务状态查询")
        result = await client.run_job("list_task_statuses", {})
        if not result.success:
            raise RuntimeError(str(result.answer))
        print(result.answer)

asyncio.run(main())
```

传入服务根地址，客户端自己附加 `/mcp`；不要重复添加路径。该示例只查询已存在记录，不提交研究任务或调用模型。

## 最小研究查询循环

1. `list_task_statuses`：确定 Task ID 和运行状态。
2. `status`：读取目标任务状态。
3. `read_task_log`：查询所需日志窗口，offset 单位是字节。
4. `get_task_graph` 或 `get_task_context`：确认上游和上下游环境。
5. `list_entries`、`preview_file`：读取 metadata 及标准产物。
6. 根据真实日期、单位和协议形成回答，并说明未取得的信息。

例如 `status` 工具参数是 `{"task_id":"<Task ID>"}`。其他参数请使用发现结果的 inputSchema，完整说明见[任务 API](../api/tasks.md)与[工作区 API](../api/workspace.md)。

预览 Parquet 返回的是受限分页数据，不一定是完整文件。汇总整个产物时先确认行数、分页和限制，不要把首批预览当全量数据。

## MCP 与实时事件

服务 MCP 的普通工具调用返回 `JobResponse`，包括 `success`、`answer` 和 `metadata`。业务 `success=false` 与 MCP 连接失败要分别处理。

实时任务日志和 Agent 增量消息走 HTTP SSE：`POST /jobs/<name>/events`。MCP 的 Streamable HTTP 传输名称不意味着 AxonX 将每个 Job 的业务事件逐条投射为实时工具结果。

需要持续观察时，使用 HTTP 流式客户端或 Studio；普通 MCP 可以按需再次查询状态。终态判定、事件类型与连接关闭见[事件协议](../api/events.md)。

## 内置 Agent 的工具桥接

内置 Claude 后端创建进程内 MCP server，保留名为 `axonx`，只映射 `job_tools` 配置的 Job。这条路径直接调用 Dispatcher，不需要再连接本机 HTTP `/mcp`。

因此，外部 MCP 工具目录与内置 Agent 可用 Job 可以不同。SDK 自身工具与权限同样独立于 Job 名单，见[Agent 配置](configuration.md)。

## 浏览器 WebMCP

Studio 在浏览器支持 `document.modelContext.registerTool` 时注册：

| 浏览器工具             | 用途                                       |
| ---------------------- | ------------------------------------------ |
| `list_axonx_task_runs` | 查询托管当前 Studio 页面的本地服务任务状态 |
| `submit_axonx_task`    | 提交注册任务与 config 对象                 |

浏览器不提供该 API 时直接跳过注册，Studio 其他功能不因此失效。这两个工具调用前端现有 API，与服务 `/mcp` 不是同一个协议入口。当前实现不传递 `target`，因此始终操作托管页面的本地服务，不跟随 Studio 的远程机器选择。浏览器环境不支持时不能用它替代普通 MCP 连接。

`submit_axonx_task` 的 config 需满足安装任务 Schema，返回提交 handle；仍需独立查询最终状态。页面生命周期结束时，通过 AbortSignal 结束工具注册生命周期。

## 连接排查

| 现象                 | 检查方向                                  |
| -------------------- | ----------------------------------------- |
| 401                  | Bearer token 与连接机器                   |
| 工具列表缺少任务能力 | 公开 Job 配置、无 token 的筛选            |
| 业务返回失败         | `success` 与 `answer` 中错误，不只看 HTTP |
| 无增量日志           | 是否使用 HTTP events 而非普通 MCP         |
| 浏览器工具不存在     | 宿主是否实现 document.modelContext        |

## 相关文档与实现

- [API 总览](../api/overview.md)、[Python 调用](../reference/python.md)
- [`MCP 客户端`](../../../axonx/components/client/mcp.py)
- [`HTTP/MCP Job 路由`](../../../axonx/components/service/http/jobs.py)
- [`浏览器工具注册`](../../../axonx_studio/src/webmcp.ts)
