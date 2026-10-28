# HTTP 与 MCP 协议

![统一 Job 协议](../../figures/api/protocol.svg)

## 路由

| 方法   | 路由              | 用途                             |
| ------ | ----------------- | -------------------------------- |
| GET    | /health           | JobResponse，answer.running      |
| GET    | /jobs             | JobResponse，目录 items/total    |
| POST   | /jobs/NAME        | 一次 JobResponse                 |
| POST   | /jobs/NAME/events | SSE，直到终态 result             |
| POST   | /upload           | 暂存单文件，answer 为 StagedFile |
| DELETE | /upload?path=...  | 清理暂存相对路径                 |
| —      | /mcp              | 无状态 Streamable HTTP MCP       |

## 认证与公开目录

配置 service.token 后，协议根路径和子路径要求 `Authorization: Bearer TOKEN`（OPTIONS 除外）。公开 Job 目录还按 enable_serve/requires_auth 筛选；服务未配置 token 时不暴露认证 Job。requires_auth=false 不绕过已配置 token 的协议层中间件。Studio 静态页面和上游代理有各自路由行为。

## 请求封装

```json
{ "arguments": { "task_id": "base#demo#check", "detail": "full" } }
```

顶层字段为 arguments 和可选 target。HTTP 转发目标必须配置在接收应用中，由后端解析凭据。客户端连接选项不能放入业务参数，MCP 工具直接暴露对应 Job 的业务参数。

## 响应与错误

JobResponse 包含 answer、success、metadata。Schema 校验可能返回 HTTP 422，路由不存在返回 404，认证失败返回 401。业务错误通常返回 success=false，即使 HTTP 为 200。检查 success 和实际 answer 形态；cli 命令还检查 exit_code、stdout、stderr；Task 还检查状态和业务输出。

## 执行 Task

向 /jobs/cli POST `{"arguments":{"argv":["exec","--task","demo","--task-name","check","--x","1","--y","2"]}}`。Job 拥有命令进程并等待完成，返回输出和退出码，状态另行查询。当前没有专用提交端点。

## MCP 与事件

MCP 暴露相同公开 Job 和普通 JobResponse Schema。实时展示使用 HTTP SSE，文件使用 /upload。关闭事件流并检查最终 result，不能将连接断开当作成功结束。

[Task API](tasks.md) · [事件](events.md) · [工作区](workspace.md) · [机器](machines.md) · [Agent](agent.md)
