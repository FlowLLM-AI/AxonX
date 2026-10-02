# Python usage reference

Python can embed an Application in-process or connect to a running HTTP/MCP service. Both paths return JobResponse, but differ in lifecycle, configuration, and execution location. This page uses the currently publicly exported classes and functions.

![Local application and remote clients](../../figures/reference/python-paths.svg)

## Import entry points

```python
from axonx import Application, BaseStep, provider
from axonx.config import resolve_app_config
from axonx.components.client import HttpClient, McpClient, RemoteServiceError
from axonx.core import run_remote_job, stream_remote_job
from axonx.components.job import ResultEvent
```

Application is exported at the top level; HTTP/MCP clients and event types are exported from their respective subpackages. The project uses Python 3.12 syntax and cannot be imported directly with older interpreters.

## Embedding Application

```python
import asyncio
from axonx import Application
from axonx.config import resolve_app_config

async def main():
    config = resolve_app_config(log_config=False, config="default")
    async with Application(**config) as app:
        response = await app.run_job("version", {})
        if not response.success:
            raise RuntimeError(str(response.answer))
        print(response.model_dump(mode="json"))

asyncio.run(main())
```

async with starts components, Jobs, and schedulers in dependency order and closes them in reverse order on exit. This example does not start an HTTP listener; CLI start calls the service's run_app. Loading default composes its components, so their dependencies must be importable in the current environment. A minimal application can retain only the Jobs it needs.

Application does not automatically read .env; resolve_app_config expands only existing environment variables. If .env is needed, load it first using the application's own environment-loading approach.

## Application methods

| Method | Parameters | Return and constraints |
| --- | --- | --- |
| start() | None | await; idempotent startup |
| close() | None | await; cleanup in reverse order; multiple cleanup errors may be aggregated |
| run_job(name, arguments=None, *, target=None) | Job name, argument mapping, optional configured target | await returns JobResponse |
| stream_job(name, arguments=None, *, target=None) | Same as above | Returns AsyncIterator; do not await the method itself |

run_job and stream_job both require a started application. A nonempty target must appear in ApplicationConfig.targets and uses its address/token. Local calls are not restricted by HTTP public_jobs filtering, but business Schemas and reserved system fields are still validated.

## HTTP client

```python
import asyncio
import os
from axonx.components.client import HttpClient

async def main():
    async with HttpClient(
        target="127.0.0.1:1024",
        token=os.environ["AXONX_SERVICE_TOKEN"],
        timeout=600.0,
    ) as client:
        definitions = await client.run_job("get_task_definition", {"task": "demo"})
        if not definitions.success:
            raise RuntimeError(str(definitions.answer))
        submitted = await client.run_job("submit", {"task": "demo", "x": 1, "y": 2})
        if not submitted.success:
            raise RuntimeError(str(submitted.answer))
        handle = submitted.answer
        completed = await client.run_job("wait_task", {
            "task_id": handle["task_id"],
            "run_id": handle["run_id"],
        })
        print(completed.success, completed.answer)

asyncio.run(main())
```

Remote answer values are decoded dictionaries/lists; a local Application.answer may retain Pydantic/dataclass objects. For uniform processing, call response.model_dump(mode="json") first, rather than assuming answer has the same Python object type on both paths.

| HttpClient method | Key signature details | Return |
| --- | --- | --- |
| run_job | name, arguments=None | JobResponse |
| stream_job | name, arguments=None | AsyncIterator[JobEvent] |
| list_jobs | None | list[JobInfo] |
| health | None | bool; failures map to false |
| copy_file | Path, filename=None, directory=None | FileCopy |
| discard_file | path: str | Cleaned-up path string |

Constructor parameters are target=None, timeout=60.0, and token=None; optional transport injects an HTTP transport, for example in tests. Calls are available only after entering async with. target must not contain `/mcp` or a Job subpath.

## Consuming events

```python
async with HttpClient(target="127.0.0.1:1024", token=token, timeout=600.0) as client:
    async for event in client.stream_job("stream_task", {"task_id": task_id}):
        if isinstance(event, ResultEvent):
            response = event.response()
            print(response.success, response.answer)
        elif event.kind == "log":
            print(event.content, end="")
```

This snippet belongs inside an asynchronous function; token/task_id come from configuration and submission results. See [SSE](../api/events.md) for detailed framing and disconnection rules. Use contextlib.aclosing for asynchronous generators whose consumption ends early to ensure the event source is closed.

## File upload

```python
from pathlib import Path

async with HttpClient(target=target, token=token) as client:
    copied = await client.copy_file(Path("dist/axonx_example-0.1.0-py3-none-any.whl"))
    try:
        installed = await client.run_job("install_plugin", {
            "path": copied.path,
            "sha256": copied.sha256,
        })
        print(installed.model_dump(mode="json"))
    finally:
        await client.discard_file(copied.path)
```

This is an installation-flow snippet; confirm the artifact before executing it. copy_file reads and uploads in chunks; service-relative paths are not client file paths. Repeated discard_file calls can clean up staging locations already consumed.

## MCP client

```python
async with McpClient(target=target, token=token, timeout=60.0) as client:
    print(await client.health())
    jobs = await client.list_jobs()
    response = await client.run_job("list_task_ids", {})
    print(response.model_dump(mode="json"))
```

McpClient health uses MCP ping; list_jobs generates JobInfo from tool Schemas; run_job validates JobResponse from structured_content/data. It has no stream_job, copy_file, or discard_file; use HttpClient for live events and byte transfer.

## One-shot remote functions

```python
response = await run_remote_job(
    "version", {}, target="node-b:1024", token=token, timeout=60.0
)
async for event in stream_remote_job(
    "stream_task", {"task_id": task_id},
    target="node-b:1024", token=token, timeout=600.0,
):
    print(event.model_dump(mode="json"))
```

arguments is a required mapping; each call creates and closes an HttpClient. Use a long-lived client for frequent queries to avoid repeated connections. This target is a direct connection address and does not depend on the local Application's targets.

## Errors and cleanup

```python
try:
    async with HttpClient(target=target, token=token) as client:
        response = await client.run_job("status", {"task_id": task_id})
except RemoteServiceError as exc:
    print("Connection or protocol failure", exc.status_code, str(exc))
else:
    if not response.success:
        print("Business failure", response.answer)
```

Connection failures, HTTP rejection, and invalid envelopes/events raise RemoteServiceError; success=false within HTTP 200 must be checked separately. Local parameter errors may directly raise ValueError; exceptions within Steps are usually handled by the Job. Closing Application closes its task manager and may cancel managed workers, so a short-lived embedded application is unsuitable for submitting a task and exiting immediately.

## Related documentation

- [Client configuration](client-configuration.md)
- [API overview](../api/overview.md)
- [Framework extensions](../development/framework-extensions.md)

Implementation references: `axonx/__init__.py`, `core/application.py`, `core/dispatch.py`, `components/client/`.
