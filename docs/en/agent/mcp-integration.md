---
title: MCP Integration for External Agents
description: Query tasks and the workspace through the AxonX service MCP, and distinguish built-in tools from WebMCP.
---

# MCP Integration for External Agents

The AxonX HTTP service provides Streamable HTTP MCP at `/mcp`, mapping public Jobs to tools. External Agents can discover and call tools in the actual service catalog to build research evidence from task status, logs, lineage, and files.

![Three integration surfaces](../../figures/agent/mcp-surfaces.svg)

## Connection details

```text
URL:       http://127.0.0.1:1024/mcp
Transport: Streamable HTTP
Header:    Authorization: Bearer <AxonX service token>
```

Host configuration formats vary. Use the host's supported remote MCP URL and headers configuration. These are connection parameters, not JSON configuration that can be copied directly into every host.

When the service enables a token, MCP also requires Bearer authentication. Without a service token, Jobs requiring authentication by default are excluded from the public catalog. An empty catalog and a rejected connection are different problems; see the [authentication guide](../guides/authentication.md).

## Discover before calling

The tool catalog comes from the running service configuration and may include queries, submission, cancellation, file deletion, shell operations, or plugin installation. External MCP exposure and the built-in Agent's `job_tools` list are separate configuration layers.

Call MCP `tools/list` first, read the tool Schema, then use `tools/call`. Do not assume that a deployment exposes a tool because its name appears in the documentation. Provide callers only with capabilities needed for the current user task.

## Using the AxonX Python MCP client

The project provides an MCP client for ordinary JobResponse results:

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
            raise RuntimeError("The service does not expose task status queries")
        result = await client.run_job("list_task_statuses", {})
        if not result.success:
            raise RuntimeError(str(result.answer))
        print(result.answer)

asyncio.run(main())
```

Pass the service root URL; the client appends `/mcp` itself. Do not add the path twice. This example only queries existing records; it does not submit research tasks or call a model.

## Minimal research query loop

1. `list_task_statuses`: determine Task IDs and execution status.
2. `status`: read the target task's status.
3. `read_task_log`: query the required log window; offsets are in bytes.
4. `get_task_graph` or `get_task_context`: confirm upstream relationships and the upstream/downstream environment.
5. `list_entries`, `preview_file`: read metadata and standard artifacts.
6. Form an answer using actual dates, units, and protocols, and state which information could not be obtained.

For example, the `status` tool accepts `{"task_id":"<Task ID>"}`. For other arguments, use the discovered inputSchema. See the [task API](../api/tasks.md) and [workspace API](../api/workspace.md) for full details.

Parquet previews return limited paginated data, which may not represent the entire file. Before summarizing an entire artifact, check row counts, pagination, and limits; do not treat the first preview batch as the full dataset.

## MCP and real-time events

Ordinary service MCP tool calls return `JobResponse`, including `success`, `answer`, and `metadata`. Handle business `success=false` separately from MCP connection failures.

Real-time task logs and incremental Agent messages use HTTP SSE: `POST /jobs/<name>/events`. The MCP transport name Streamable HTTP does not imply that AxonX projects every Job business event into a real-time tool result.

For continuous observation, use an HTTP streaming client or Studio. Ordinary MCP can query status again as needed. See the [event protocol](../api/events.md) for terminal-state detection, event types, and connection closure.

## Built-in Agent tool bridge

The built-in Claude backend creates an in-process MCP server with the reserved name `axonx`, mapping only Jobs configured in `job_tools`. This path calls Dispatcher directly without connecting to the local HTTP `/mcp`.

The external MCP tool catalog can therefore differ from the Jobs available to the built-in Agent. The SDK's own tools and permissions are also independent of the Job list; see [Agent configuration](configuration.md).

## Browser WebMCP

Studio registers these tools when the browser supports `document.modelContext.registerTool`:

| Browser tool           | Purpose                                                                |
| ---------------------- | ---------------------------------------------------------------------- |
| `list_axonx_task_runs` | Query task status on the local service hosting the current Studio page |
| `submit_axonx_task`    | Submit a registered task and a config object                           |

If the browser lacks this API, registration is simply skipped; other Studio features continue to work. These tools call existing frontend APIs and are not the same protocol entry point as the service `/mcp`. The current implementation does not pass `target`, so it always operates on the local service hosting the page and does not follow Studio's remote machine selection. When unsupported by the browser, they cannot replace an ordinary MCP connection.

The config for `submit_axonx_task` must satisfy the installed task Schema. It returns a submission handle; query final status separately. When the page lifecycle ends, AbortSignal ends the tool registration lifecycle.

## Connection troubleshooting

| Symptom                                      | What to check                                              |
| -------------------------------------------- | ---------------------------------------------------------- |
| 401                                          | Bearer token and the connected machine                     |
| Task capabilities missing from the tool list | Public Job configuration and filtering without a token     |
| Business result reports failure              | Errors in `success` and `answer`, not just HTTP status     |
| No incremental logs                          | Whether HTTP events are being used instead of ordinary MCP |
| Browser tools absent                         | Whether the host implements document.modelContext          |

## Related documentation and implementation

- [API overview](../api/overview.md), [Python calls](../reference/python.md)
- [MCP client](../../../axonx/components/client/mcp.py)
- [HTTP/MCP Job routes](../../../axonx/components/service/http/jobs.py)
- [Browser tool registration](../../../axonx_studio/src/webmcp.ts)
