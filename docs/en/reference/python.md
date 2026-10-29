# Python Reference

## Import entry points

```python
from axonx.app.core.application import Application
from axonx.app.config.loader import ConfigLoader
from axonx.app.steps.base import BaseStep
from axonx.app.components.registry import provider
from axonx.client.http import HttpClient, run_remote_job, stream_remote_job
from axonx.client.mcp import McpClient
from axonx.client.base import RemoteServiceError, RemoteConnectionError
from axonx.client.models import JobResponse, StagedFile
from axonx.client.events import ResultEvent
```

Use Python 3.12+. The root package exports version metadata; capability namespaces do not re-export every implementation.

## Embedding Application

```python
import asyncio
from axonx.app.core.application import Application

async def main():
    async with Application(log_to_console=False, log_to_file=False) as app:
        print(app.is_started, app.workspace_path)

asyncio.run(main())
```

This minimal graph needs no product adapters and starts no HTTP listener. To load configured Jobs, resolve configuration with `ConfigLoader().resolve(config="default", log_config=False)` and pass the resulting mapping. Inject a TaskCatalog, update backend or scheduled launcher when using those capabilities; they belong to the host. Task-only clients do not need an Application. Application does not automatically load .env.

## Application methods

`start()` and `close()` manage dependency-ordered lifecycles. `run_job(name, arguments=None, *, target=None)` returns JobResponse; `stream_job(...)` returns an async iterator and is not awaited directly. Both require a running application. A forwarded target must be configured in ApplicationConfig.targets.

## HTTP client

```python
import asyncio
import os
from axonx.client.http import HttpClient

async def main():
    async with HttpClient(
        target="127.0.0.1:1024",
        token=os.environ["AXONX_SERVICE_TOKEN"],
        timeout=600.0,
    ) as client:
        response = await client.run_job("cli", {"argv": [
            "exec", "--task", "demo", "--task-name", "python-api",
            "--x", "1", "--y", "2",
        ]})
        if not response.success:
            raise RuntimeError(str(response.answer))
        assert response.answer["exit_code"] == 0
        status = await client.run_job("status", {
            "task_id": "base#demo#python-api", "detail": "full",
        })
        print(status.model_dump(mode="json"))

asyncio.run(main())
```

Methods are `run_job`, `stream_job`, `list_jobs`, `health`, `copy_file(Path, filename=None, directory=None)` and `discard_file(path)`. Constructor fields are target, timeout, token and optional HTTP transport injection. Use async with for connection ownership. Supply credentials explicitly; library clients do not read CLI token variables automatically. Remote answers are decoded data; local answers may contain model objects. Normalize with model_dump(mode="json") when needed.

## Consuming events

```python
from contextlib import aclosing
from axonx.client.events import ResultEvent

# Inside an async function with a started HttpClient named client:
async with aclosing(client.stream_job("stream_task", {"task_id": task_id})) as events:
    async for event in events:
        if isinstance(event, ResultEvent):
            print(event.response().model_dump(mode="json"))
        elif event.kind == "log":
            print(event.content, end="")
```

## File upload

`copy_file` returns StagedFile with path, size and absolute location. Use location for target-side plugin install and path for staged-file cleanup or sync. Clean up with discard_file in finally after command completion is confirmed; retain the upload if the command outcome is unknown. A complete remote installation example is in [Plugin management](../plugins/management.md).

## MCP client

`McpClient` shares run_job, list_jobs and health over `/mcp` using the service base target. MCP returns ordinary Job responses. Use HTTP SSE for live events; use HTTP upload for files.

## One-shot remote functions

`await run_remote_job("version", {}, target=..., token=...)` opens and closes one HTTP client. `stream_remote_job` is an async generator; close it with aclosing if consumption stops early. These helpers do not perform CLI value conversion.

## Errors and cleanup

RemoteConnectionError identifies unreachable/time-out connections. RemoteServiceError covers protocol/HTTP failures and carries optional status_code. Check JobResponse.success separately. A dropped command stream can leave execution acceptance uncertain; inspect Task start time before retrying. Cancellation closes the client connection. The default cli Job continues executing; service shutdown still terminates its manual command groups.

Sources: [Application](../../../axonx/app/core/application.py), [HTTP](../../../axonx/client/http.py), [MCP](../../../axonx/client/mcp.py).
