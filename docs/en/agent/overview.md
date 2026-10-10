---
title: Agent Development Overview
description: Choose external CLI / MCP access or built-in agent sessions in Studio.
---

# Agent Development Overview

AxonX gives Agents tools and a runtime to develop quantitative plugins, execute experiments, and analyze results. Combine a research prompt with the AxonX Skill or development guide, then use an external host or configured built-in sessions in Studio. Both paths can support plugin development when source and code tools are available; model configuration and sessions are managed by different parties.

![Independent Agent integration paths](../../figures/agent/mcp-surfaces.svg)

## Start with a research objective

Prepare source and code tools, then use [Skill and research prompt](research-prompt.md) to define the baseline, hypothesis, windows, metrics, and execution service. After development, follow [Research](../research/overview.md) to execute and evaluate.

## Choose a path

|                     | External agent                                                         | Built-in agent                                                          |
| ------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Entry point         | Hosts such as Codex or Claude Code                                     | Studio → Agent, or the `agent_chat` Job                                 |
| Model configuration | Managed by the external host                                           | Server-side Claude Agent SDK configuration                              |
| AxonX connection    | Direct CLI access or service `/mcp`                                    | Built-in component invokes configured Jobs through Dispatcher           |
| Instructions        | [AxonX Skill](../../../skills/axonx/SKILL.md) and development guide    | Optionally load the development guide bundled with the package          |
| Tool scope          | Available CLI commands or public service MCP catalog                   | `job_tools`, SDK tools, and permission settings                         |
| Session records     | Managed by the external host                                           | Managed by AxonX session storage                                        |
| Reading path        | [External agents](external.md) → [MCP integration](mcp-integration.md) | [Built-in configuration](configuration.md) → [Built-in usage](usage.md) |

External integration does not require `CLAUDE_CODE_*` settings or built-in guide loading. The built-in agent's eight default Job tools query tasks and files; the public external MCP catalog may also include submission, cancellation, and installation. Actual capabilities depend on the selected path's configuration and schemas.

## The shared research loop

1. Define the research objective and controls; provide the Skill, source checkout, and code tools.
2. Develop or optimize the plugin, validate the code, and install it in the selected execution service.
3. Discover live Task schemas, check upstream compatibility, and submit the required stages.
4. Keep the returned `task_id` and `run_id`, and wait for each upstream execution to succeed.
5. Inspect artifacts and compare results; use the evidence to guide further code or parameter changes.

Keep the same `--target` across stages when using direct CLI access. Studio forwards requests through its same-origin backend to the selected machine. Tasks, data, and plugins live in the execution service's environment; agent integration does not migrate them automatically.

## Continue by goal

- Develop research plugins: [external agents](external.md) or [built-in development](usage.md#develop-or-optimize-a-plugin), plus the [development and operations guide](../dev_guide.md).
- Analyze existing records in a browser: [built-in agent usage](usage.md).
- Design ablations and independent confirmation: [experiment design and confirmation](../research/experiments.md).
- Look up connections, responses, and events: [MCP integration](mcp-integration.md), [API overview](../api/overview.md).
