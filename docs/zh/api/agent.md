# Agent API

会话管理与一轮对话均通过 Job 调用。创建与续接使用相同 agent_chat；实时呈现通过 HTTP SSE 完成。

![Agent API调用示意](../../figures/api/events.svg)

## 调用约定

以下均为 `POST /jobs/{name}`，请求体是 `{"arguments":{...}}`。远程转发时在封装顶层添加 `target`，不能放进 arguments。每个响应使用 [JobResponse](overview.md#响应与错误)，表格默认值依据当前内置配置和 Step。部署可修改 Job Schema，运行服务的 `/jobs` 是最终依据。

所有示例 JSON 均为结构示例；任务、会话、文件路径与哈希必须替换为本服务实际返回的值。完整通用 TaskStatus 字段见 [Task 协议](../reference/task-contracts.md)。

## 接口清单

| Job | 用途 |
| --- | --- |
| `agent_chat` | 运行一轮 Agent 对话，省略 session_id 创建会话。 |
| `list_agent_sessions` | 按最新优先列出会话。 |
| `get_agent_session` | 读取会话摘要、历史消息与展示块。 |
| `rename_agent_session` | 设置自定义标题。 |
| `tag_agent_session` | 设置或清除标签。 |
| `delete_agent_session` | 永久删除会话及子 Agent 记录。 |
| `fork_agent_session` | 从历史创建一个新会话。 |
| `cancel_agent_turn` | 中断会话当前轮次。 |

## agent_chat

运行一轮 Agent 对话，省略 session_id 创建会话。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `message` | string | 是 | `—（省略）` | 本轮用户消息；minLength=1 |
| `session_id` | string | 否 | `—（省略）` | 后端会话 UUID；UUID 格式 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "message": "列出本工作区中的任务，并说明状态。"
  }
}
```

**响应**

answer 是后端最终文本；metadata 来自 SDK ResultMessage，包含 session_id 与本轮使用/结果信息。SSE 同时输出 agent_message。

```json
{
  "answer": "本工作区暂无任务。",
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

续接需传回 metadata.session_id；同一会话按后端锁串行执行；并发调用等待前一轮结束。agent_depth 由系统注入，默认 0，默认 max_depth=3；它不属于公开请求参数。默认后端 Claude，需要有效模型配置。

## list_agent_sessions

按最新优先列出会话。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `limit` | integer | 否 | `—（省略）` | 返回的会话数量；minimum=1, maximum=200 |
| `offset` | integer | 否 | `0` | 跳过的会话数量；minimum=0 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "limit": 20,
    "offset": 0
  }
}
```

**响应**

answer 为 SDK 会话摘要数组；每项增加 backend 字段。

```json
{
  "answer": [],
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

省略 limit 表示向 SDK 传 None，不是假定 20。返回摘要字段由当前 SDK 提供，常见 session_id、summary、自定义标题和时间。

## get_agent_session

读取会话摘要、历史消息与展示块。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 是 | `—（省略）` | 后端会话 UUID；UUID 格式 |
| `limit` | integer | 否 | `—（省略）` | 读取的历史消息数量；minimum=1, maximum=1000 |
| `offset` | integer | 否 | `0` | 跳过的历史消息数量；minimum=0 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab",
    "limit": 100
  }
}
```

**响应**

answer 包含 info、messages、blocks；info 增加 backend，messages 保留 SDK 数据，blocks 是前端可显示投影。

```json
{
  "answer": {
    "info": {
      "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab",
      "backend": "claude"
    },
    "messages": [],
    "blocks": []
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

offset 按消息条数；省略 limit 传 None。历史块不等同于 SSE presentation 补丁。会话不存在为 KeyError 业务失败。

## rename_agent_session

设置自定义标题。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 是 | `—（省略）` | 后端会话 UUID；UUID 格式 |
| `title` | string | 是 | `—（省略）` | 自定义会话标题；minLength=1 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab",
    "title": "实验复盘"
  }
}
```

**响应**

answer 为 {session_id: UUID}；fork 返回新会话 UUID，其余返回请求 UUID。

```json
{
  "answer": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab"
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

title 至少一个字符。

## tag_agent_session

设置或清除标签。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 是 | `—（省略）` | 后端会话 UUID；UUID 格式 |
| `tag` | string/null | 是 | `—（省略）` | 会话标签；null 清除 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab",
    "tag": null
  }
}
```

**响应**

answer 为 {session_id: UUID}；fork 返回新会话 UUID，其余返回请求 UUID。

```json
{
  "answer": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab"
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

tag 为必填字段；null 表示清除，而不是省略。

## delete_agent_session

永久删除会话及子 Agent 记录。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 是 | `—（省略）` | 后端会话 UUID；UUID 格式 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab"
  }
}
```

**响应**

answer 为 {session_id: UUID}；fork 返回新会话 UUID，其余返回请求 UUID。

```json
{
  "answer": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab"
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

运行中的会话拒绝删除，先停止轮次再删除。

## fork_agent_session

从历史创建一个新会话。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 是 | `—（省略）` | 后端会话 UUID；UUID 格式 |
| `up_to_message_id` | string | 否 | `—（省略）` | 可选分叉截止消息 UUID；UUID 格式 |
| `title` | string | 否 | `—（省略）` | 自定义会话标题；minLength=1 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab",
    "title": "分支实验"
  }
}
```

**响应**

answer 为 {session_id: UUID}；fork 返回新会话 UUID，其余返回请求 UUID。

```json
{
  "answer": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab"
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

up_to_message_id 可选，指定消息 UUID 时截止到该消息；返回新的 session_id。

## cancel_agent_turn

中断会话当前轮次。

| 参数 | 类型 | 必填 | 默认值 | 约束与含义 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 是 | `—（省略）` | 后端会话 UUID；UUID 格式 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab"
  }
}
```

**响应**

answer 为 {session_id: UUID}；fork 返回新会话 UUID，其余返回请求 UUID。

```json
{
  "answer": {
    "session_id": "17eeef86-6bc7-4565-a4a2-41249b5576ab"
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

会话未运行返回 KeyError；不会取消已经独立提交的研究 Task。

## 失败响应示例

session_id 不满足 UUID 正则时返回 HTTP 422。符合 UUID 但本轮未运行，cancel_agent_turn 返回业务失败：

```json
{"answer":"KeyError: 'Agent session is not running: 17eeef86-6bc7-4565-a4a2-41249b5576ab'","success":false,"metadata":{}}
```

模型连接、SDK 权限与会话恢复失败可能产生其他错误；流式请求一旦开始，用最终 result.success 判断，不能从连接状态推断轮次成功。SDK 摘要/消息结构随依赖版本变化，稳定的 AxonX 顶层字段是 JobResponse 与 info/messages/blocks 分组。

## 相关文档

- [协议、鉴权与错误](overview.md)
- [Agent 使用](../agent/usage.md)
- [CLI 参考](../reference/cli.md)
- [事件协议](events.md)

实现依据：`axonx/config/default.yaml`、`axonx/steps/agent/` 与 `axonx/components/service/http/jobs.py`。
