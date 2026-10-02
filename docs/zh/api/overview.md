# API 协议总览

AxonX 将 Job 暴露为普通 HTTP JSON、HTTP SSE 与 MCP 工具。三种调用共享业务 Schema 与 JobResponse；Task、Agent 和文件操作各自的参数在能力页查阅。服务必须已启动，调用前先确认 token 与实际公开目录。

![Job 的三种调用入口](../../figures/api/protocol.svg)

![Studio API catalog](../../figures/studio/api-catalog.png)

Studio 的 **API interfaces** 展示当前机器公开的 Job，并由参数 Schema 生成表单。上图尚未发起调用；完整调用响应见[Studio 入门](../getting-started/studio.md)。

## 路由

| 方法 | 路径 | 用途 | 成功响应 |
| --- | --- | --- | --- |
| GET | `/health` | 当前 Application 是否启动 | JobResponse，answer.running |
| GET | `/jobs` | 实际公开 Job 目录 | JobResponse，answer.items/total |
| POST | `/jobs/{name}` | 普通调用 | JobResponse |
| POST | `/jobs/{name}/events` | 实时事件 | text/event-stream，最后 result |
| POST | `/files` | 上传原始字节暂存 | JobResponse，answer 为 FileCopy |
| DELETE | `/files?path=...` | 清理暂存文件 | JobResponse，answer.path |
| MCP | `/mcp` | Streamable HTTP 工具接口 | MCP 包含 JobResponse |
| 多种 HTTP 方法 | `/proxy/{name}/{path}` | 已配置上游代理 | 上游响应 |

所有业务请求默认向当前服务执行。`GET /jobs?target=http%3A%2F%2Fnode-b%3A1024` 查询配置目标的目录；Job 请求中的 target 使用相同配置匹配规则。proxy 是单独的上游转发能力，见 [HTTP 代理](../guides/http-proxy.md)。

## 鉴权与公开目录

配置 `service.token` 后，`/health`、`/jobs`、`/files`、`/mcp` 的根路径和子路径都要求：

```http
Authorization: Bearer your-service-token
```

OPTIONS 请求不做该校验。Studio 静态页面与 `/proxy` 不在这组协议保护根路径中；proxy 使用上游请求的凭据。`requires_auth=false` 不会绕过已配置的服务 token。

公开 Job 由两个条件筛选：

1. `enable_serve=true`。
2. 服务已配置 token，或 Job 的 `requires_auth=false`。

Job 默认 `requires_auth=true`，因此默认配置未设置 token 时不能假定所有默认 Job 都进入目录。`enable_stream=false` 的 Job 可普通调用，但本地 `/events` 返回 404。修改配置后应重启服务，目录在构建 HTTP 应用时确定。

## 请求封装

```json
{
  "arguments": {"task": "demo", "x": 1, "y": 2},
  "target": "http://node-b:1024"
}
```

`arguments` 是业务参数字典，默认为 `{}`；`target` 可省略，默认为本机执行。封装拒绝额外顶层字段。target 必须在本服务 `targets` 中，远端 token 由本服务配置保存，浏览器只提交地址。

CLI `--target` 则直接连接地址，使用客户端自己的 token，不需要本服务 targets。MCP 工具只接收 Job 业务参数，没有上述 HTTP target 封装。

## 最小调用

假设服务地址为 `http://127.0.0.1:1024`，token 已保存到 `AXONX_SERVICE_TOKEN`。

```bash
curl -s http://127.0.0.1:1024/health \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"

curl -s http://127.0.0.1:1024/jobs \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"

curl -s -X POST http://127.0.0.1:1024/jobs/version \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"arguments":{}}'
```

健康响应：

```json
{"answer":{"running":true},"success":true,"metadata":{}}
```

目录返回 JobCatalog；下面只展示一项以说明字段形状，实际 Schema 更完整：

```json
{
  "answer": {
    "items": [{
      "name": "version",
      "description": "Return the installed AxonX version.",
      "input_schema": {"type":"object","properties":{}},
      "output_schema": {"type":"object"}
    }],
    "total": 1
  },
  "success": true,
  "metadata": {}
}
```

output_schema 描述通用 JobResponse，不保证 answer 中各能力类型都被独立建模。Task 定义的 output_schema 另由任务目录接口提供。

## 响应与错误

| 字段 | 类型 | 默认值 | 解释 |
| --- | --- | --- | --- |
| answer | 任意 JSON 可序列化值 | `""` | 业务答案或错误文本 |
| success | boolean | true | Job 的最终业务结果 |
| metadata | object | `{}` | 补充信息；Agent 在此提供 session_id 等 |

```json
{"answer":"KeyError: 'base#demo#missing'","success":false,"metadata":{}}
```

这是 HTTP 200 中的业务失败示例。客户端必须同时判断 HTTP 状态与 success，不能只看 200。

| HTTP 状态 | 常见触发 | 响应与处理 |
| --- | --- | --- |
| 401 | token 缺失或不匹配 | `{"detail":"Invalid bearer token"}`；检查连接目标与 token 来源 |
| 404 | Job 不公开、名称未知或流式关闭 | `{"detail":"Unknown job"}`；重新查询目录 |
| 422 | 请求封装、参数 Schema、target 配置错误 | detail 文本或 FastAPI 校验详情；修改请求 |
| 502 | 普通远程调用连接或协议失败 | detail 文本；检查远端健康与凭据 |
| 413 | 上传超出大小限制 | detail 文本；缩小制品 |
| 409 | 暂存目的位置冲突 | detail 文本；检查暂存内容与符号链接 |

执行 Step 内部异常通常折叠为 success=false。流式调用开始后异常会变成失败 result 事件，无法再用 HTTP 状态表达。没有终态 result 的断流不是成功。

## MCP 与事件

MCP 按公开 Job 自动注册工具名、描述与 parameters，工具返回普通 JobResponse。MCP 的 Streamable HTTP 是传输模式，不能替代 `/jobs/{name}/events` 的 AxonX SSE 事件协议。实时任务日志、Agent 思考和工具块使用 [事件协议](events.md)。

文件上传不通过 Job arguments 或 MCP 工具直接传字节，先使用 [文件传输路由](workspace.md#文件上传与清理)。

## 相关文档

- [任务 API](tasks.md)
- [工作区 API](workspace.md)
- [机器 API](machines.md)
- [Agent API](agent.md)
- [插件与同步 API](plugins-sync.md)
- [鉴权规则](../guides/authentication.md)
- [Python 调用](../reference/python.md)

实现依据：`axonx/constants.py`、`components/service/http/app.py`、`jobs.py`、`files.py`、`components/job/contracts.py`。
