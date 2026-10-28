# Streaming Events

![Streaming events](../../figures/api/events.svg)

## Connection and framing

POST `/jobs/NAME/events` with the ordinary Job envelope and token; consume `text/event-stream`. Frames contain `event: KIND` and one JSON `data:` line followed by a blank line. Kinds are progress, log, artifact, agent_message and result.

```text
event: result
data: {"kind":"result","answer":{"result":3},"success":true,"metadata":{}}

```

The example is a business result shape, not an execution handle. A cli Job's answer instead contains stdout/stderr/exit_code and truncation flags.

## Event types

| Kind          | Fields                                                                            |
| ------------- | --------------------------------------------------------------------------------- |
| progress      | Step name, state, percentage, timing, metrics and optional named substep parent   |
| log           | content, start_offset, next_offset, file_size, before/after flags, reset, channel |
| artifact      | path, sha256, size, optional media_type, extra                                    |
| agent_message | session_id, type_name, message_uuid, role, sequence, presentation                 |
| result        | answer, success, metadata                                                         |

Agent presentation patches have operation (start/append/replace/finish), block_id, block_type, delta and payload. Block types are thinking/text/tool/system/error. Merge patches by session, message and block identity; sequence orders message updates. Render presentation data, not backend implementation objects.

## Python consumption

```python
from contextlib import aclosing
from axonx.client.events import ResultEvent
from axonx.client.http import HttpClient

# Inside an async function; target/token/task_id come from the selected service:
async with HttpClient(target=target, token=token, timeout=600.0) as client:
    async with aclosing(client.stream_job("stream_task", {"task_id": task_id})) as events:
        async for event in events:
            if isinstance(event, ResultEvent):
                print(event.success, event.answer)
            elif event.kind == "log":
                print(event.content, end="")
```

## Browser consumption

Use fetch with an AbortSignal and parse SSE across arbitrary network chunk boundaries, including split UTF-8 characters. A final result determines success; event-stream HTTP status only confirms connection admission. Studio's shared event transport owns decoding and terminal result validation.

## Disconnection, cancellation and retries

Close streams when consumers leave. Cancelling an observation does not kill the observed Task. Cancelling a service-owned cli invocation can terminate its process group; cancelling an Agent turn interrupts the model session and may affect tools owned by that turn. Independent executions need explicit lifecycle management. Do not repeat uncertain exec/install requests without inspecting persisted evidence or the target environment.

Sources: [Job events](../../../axonx/client/events.py), [Task events](../../../axonx/task/models/events.py), [HTTP framing](../../../axonx/app/components/service/http/jobs.py).
