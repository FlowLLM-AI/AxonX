# SSE 事件协议

使用 `POST /jobs/{name}/events` 消费同一次 Job 的实时进度、日志、产物或 Agent 消息。连接建立后持续读取，收到 `result` 后停止，并根据其 `success` 判定调用结果。

![事件流的完成判定](../../figures/api/events.svg)

## 连接与 framing

请求封装和鉴权与 [普通 HTTP](overview.md) 相同。成功响应的 Content-Type 为 `text/event-stream`。每个事件的 event 行等于 kind，data 是单行 JSON，以空行结束：

```text
event: progress
data: {"kind":"progress","name":"submitted","started_at":null,"finished_at":null,"percentage":100.0}

event: result
data: {"kind":"result","answer":{"task_id":"base#demo#example","run_id":"f5caee3a7b3c40849d0fb3bdc0f0cd23","task":"demo"},"success":true,"metadata":{}}

```

上例是 submit Job 的接受结果；不是 demo 已成功完成。跟踪后台 Task 时调用 stream_task，其最终 result.answer 为终态状态。

```bash
curl -N -X POST http://127.0.0.1:1024/jobs/stream_task/events \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"arguments":{"task_id":"base#demo#example"}}'
```

原生 EventSource 只支持 GET，不能直接构造本协议的 POST 与 Authorization；浏览器应使用 fetch 加流读取，Studio 已实现相应解码。

## 事件类型

### progress

| 字段                     | 类型与默认值     | 含义             |
| ------------------------ | ---------------- | ---------------- |
| kind                     | `"progress"`     | 判别字段         |
| name                     | 非空 string      | 步骤/进度名称    |
| started_at / finished_at | datetime 或 null | 时间，默认 null  |
| percentage               | number 或 null   | 0–100，默认 null |

progress 可多次更新同一个名称。不要将单个步骤的百分比当成整个研究链的百分比。

### log

| 字段                             | 类型与默认值     | 含义                         |
| -------------------------------- | ---------------- | ---------------------------- |
| content                          | string，空字符串 | 已解码文本                   |
| start_offset / next_offset       | integer，0       | 本块开始与下一块读取字节偏移 |
| file_size                        | integer，0       | 已知日志文件大小             |
| has_more_before / has_more_after | boolean，false   | 窗口前后还有内容             |
| reset                            | boolean，false   | 日志重置提示                 |
| channel                          | string，`"task"` | 日志通道                     |

读取 API 的 TaskLogChunk 与 log 事件共享主要字段，后者再加 kind/channel。分页用字节偏移，不用 JavaScript 字符长度。出现 reset 时重置本地窗口状态，再按本块偏移处理。

### artifact

| 字段       | 类型与默认值      | 含义     |
| ---------- | ----------------- | -------- |
| path       | string，必填      | 产物路径 |
| sha256     | string，`""`      | 校验和   |
| size       | integer，0        | 字节大小 |
| media_type | string/null，null | 媒体类型 |
| extra      | object，`{}`      | 补充描述 |

协议支持 artifact，但不是每个内置 Job 都会发送。产物是否可用还要检查任务终态与 metadata。

### agent_message

| 字段         | 类型                          | 含义         |
| ------------ | ----------------------------- | ------------ |
| session_id   | 非空 string                   | 当前会话     |
| type_name    | string                        | 后端消息类型 |
| message      | object                        | 后端消息数据 |
| sequence     | integer ≥0                    | 当前事件序号 |
| presentation | AgentBlockPatch 数组，默认 [] | 显示块补丁   |

每个补丁含 operation、block_id、block_type、delta（默认 `""`）、payload（默认 `{}`）。block_type 为 thinking/text/tool/system/error；operation 为：

| operation | 客户端行为                             |
| --------- | -------------------------------------- |
| start     | 为 block_id 建立块，记录类型与 payload |
| append    | 将 delta 添加到同一块文本              |
| replace   | 用权威内容替换块；按 payload 更新显示  |
| finish    | 完成块，保留最终内容                   |

后端可能在先发送文本增量后，再给出完整 Assistant 消息，因此 replace 很重要；不能将所有文本重复追加。presentation 是 AxonX 的展示投影，message 则保留后端数据。sequence 不构成通用跨请求续传游标，block_id 也不是消息 UUID。

### result

result 是 JobResponse 加 `kind="result"`，包含 answer、success、metadata。服务发送第一个 result 后关闭事件源。发生异常时 result 可携带 `success=false` 和错误文本；没有结果时服务会尽力发送“Stream produced no terminal result”的失败结果。

## Python 消费

```python
import asyncio
import os
from axonx.components.client import HttpClient
from axonx.components.job import ResultEvent

async def main():
    async with HttpClient(
        target="127.0.0.1:1024",
        token=os.environ["AXONX_SERVICE_TOKEN"],
        timeout=600.0,
    ) as client:
        async for event in client.stream_job(
            "stream_task", {"task_id": "base#demo#example"}
        ):
            if isinstance(event, ResultEvent):
                print(event.success, event.answer)
            else:
                print(event.model_dump(mode="json"))

asyncio.run(main())
```

HttpClient 检查 Content-Type、校验 data 为已知事件模型，并在没有 result 的断流上抛 RemoteServiceError。

## 浏览器消费

以下示例展示 framing 与终态判断；生产应用还应使用 Studio 的事件模型和 Agent reducer 校验字段。

```typescript
async function follow(token: string, taskId: string) {
  const response = await fetch("/jobs/stream_task/events", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ arguments: { task_id: taskId } }),
  });
  if (!response.ok || !response.body) throw new Error("连接失败");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let resultSeen = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      let boundary: number;
      while ((boundary = pending.indexOf("\n\n")) >= 0) {
        const frame = pending.slice(0, boundary);
        pending = pending.slice(boundary + 2);
        const data = frame
          .split("\n")
          .find((line) => line.startsWith("data: "));
        if (!data) continue;
        const event = JSON.parse(data.slice(6));
        if (event.kind === "result") {
          resultSeen = true;
          return event;
        }
        console.log(event);
      }
    }
    if (!resultSeen) throw new Error("未收到最终结果");
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
}
```

## 断连、取消与重试

关闭流会取消本次 Job 的执行或消费，不承诺取消 submit 已启动的独立 Task。明确取消 Task 用 cancel；Agent 停止轮次用 cancel_agent_turn。断线后重新请求可能重放日志或重新运行 Job，不能自动重试会写入、安装或发送消息的 Job。

协议没有 Last-Event-ID、全局事件 ID、exactly-once 或通用重放保证。read_task_log 的 next_offset 可以用于日志窗口续读，但不等于所有事件可续传。

## 相关文档

- [任务 API](tasks.md)
- [Agent API](agent.md)
- [Python 调用](../reference/python.md)

实现依据：`components/job/events.py`、`components/service/http/jobs.py`、`components/client/http.py`、`axonx_studio/src/shared/api/`。
