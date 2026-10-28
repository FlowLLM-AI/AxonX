# 流式事件

![流式事件](../../figures/api/events.svg)

## 连接与帧格式

向 `/jobs/NAME/events` POST 普通 Job 封装和 token，消费 `text/event-stream`。每帧含 `event: KIND`、一行 JSON `data:` 和空行，kind 为 progress、log、artifact、agent_message、result。

```text
event: result
data: {"kind":"result","answer":{"result":3},"success":true,"metadata":{}}

```

示例是业务结果形态，不是执行句柄。cli Job 的 answer 则包含 stdout/stderr/exit_code 和截断标志。

## 事件类型

| Kind          | 字段                                                                    |
| ------------- | ----------------------------------------------------------------------- |
| progress      | 步骤名、状态、百分比、时间、metrics 和可选子步骤 parent                 |
| log           | content、start_offset、next_offset、file_size、前后标志、reset、channel |
| artifact      | path、sha256、size、可选 media_type、extra                              |
| agent_message | session_id、type_name、message_uuid、role、sequence、presentation       |
| result        | answer、success、metadata                                               |

Agent 展示补丁包含 operation（start/append/replace/finish）、block_id、block_type、delta、payload。block 类型为 thinking/text/tool/system/error。按会话、消息和 block 身份合并补丁，用 sequence 排序更新。展示层读取 presentation 数据，不直接依赖后端实现对象。

## Python 消费

```python
from contextlib import aclosing
from axonx.client.events import ResultEvent
from axonx.client.http import HttpClient

# 在异步函数中，target/token/task_id 来自所选服务：
async with HttpClient(target=target, token=token, timeout=600.0) as client:
    async with aclosing(client.stream_job("stream_task", {"task_id": task_id})) as events:
        async for event in events:
            if isinstance(event, ResultEvent):
                print(event.success, event.answer)
            elif event.kind == "log":
                print(event.content, end="")
```

## 浏览器消费

用带 AbortSignal 的 fetch，跨任意网络分块解析 SSE，包括被拆开的 UTF-8 字符。最终 result 决定成功，HTTP 状态仅说明允许建立连接。Studio 共享事件传输负责解码和终态校验。

## 断开、取消与重试

消费者离开时关闭流。取消观察不会停止被观察 Task；取消服务拥有的 cli 调用可能终止其进程组。取消 Agent 轮次中断模型会话，也可能影响该轮次拥有的工具；独立执行需显式管理生命周期。exec/install 请求结果不明确时，先检查持久化证据或目标环境再重试。

源码：[Job 事件](../../../axonx/client/events.py)、[Task 事件](../../../axonx/task/models/events.py)、[HTTP 帧](../../../axonx/app/components/service/http/jobs.py)。
