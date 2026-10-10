# Reference

Use reference pages to look up command syntax, configuration fields, responses, and events. For a first execution, follow the [quickstart](../getting-started/quickstart.md); for a complete research chain, follow the [research workflow](../research/workflow.md).

## Choose an interface

| Interface or setting                           | Reference                                                 |
| ---------------------------------------------- | --------------------------------------------------------- |
| CLI commands and local execution               | [CLI](cli.md)                                             |
| Programmatic service calls                     | [Python](python.md)                                       |
| Client addresses, tokens, and timeouts         | [Client configuration](client-configuration.md)           |
| Application, component, and Job assembly       | [Server configuration](configuration.md)                  |
| HTTP discovery and JobResponse                 | [API overview](../api/overview.md)                        |
| Task submission, state, context, and graphs    | [Task API](../api/tasks.md)                               |
| Live progress and log events                   | [SSE events](../api/events.md)                            |
| Workspace listing and previews                 | [Workspace API](../api/workspace.md)                      |
| Machines and resource readings                 | [Machine API](../api/machines.md)                         |
| Plugin management and snapshot synchronization | [Plugins and synchronization API](../api/plugins-sync.md) |
| Built-in Agent sessions                        | [Agent API](../api/agent.md)                              |

External agents discover service tools through [MCP integration](../agent/mcp-integration.md). MCP exposes public Jobs; live SSE uses the HTTP event endpoints.

## Read responses at the right layer

HTTP transport status, JobResponse `success`, and Task terminal state answer different questions. A successful `submit` returns a TaskHandle; use its `task_id` and `run_id` to wait for that execution and inspect its final state. Discover schemas on the connected service because installed plugins and configured Jobs determine available capabilities.

## Extension contracts

| Implementation                                | Reference                                            |
| --------------------------------------------- | ---------------------------------------------------- |
| Task inputs, outputs, identity, and lifecycle | [Task contracts](task-contracts.md)                  |
| Plugin packaging, registration, and discovery | [Plugin manifest](plugin-manifest.md)                |
| Research artifacts and Studio views           | [Research artifact contracts](research-artifacts.md) |

For plugin authoring steps, see the [development and operations guide](../dev_guide.md). For execution semantics, see [Jobs and Tasks](../concepts/jobs-and-tasks.md).
