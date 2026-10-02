# Introducing AxonX

AxonX is a Harness framework for quantitative financial research. It represents data processing, factor analysis, training, prediction, and backtesting as Tasks with input and output contracts, and connects the CLI, Studio, and Agent through Job interfaces so research code, task execution, logs, and artifacts can be tracked in one workspace.

![AxonX research and execution overview](../../figures/getting-started/overview.svg)

## Start with your work

| What I want to do                                    | Where to start                                                                                                  |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Install and run my first task                        | [Quick start](quickstart.md)                                                                                    |
| Submit tasks and view logs and results in a browser  | [Getting started with Studio](studio.md)                                                                        |
| Complete the research chain from data to backtesting | [Quantitative research workflow](../research/workflow.md)                                                       |
| Execute tasks on another machine                     | [Using remote machines](../guides/remote-machines.md)                                                           |
| Let an Agent read tasks, artifacts, and context      | [Agent research assistant](../agent/usage.md)                                                                   |
| Call capabilities from my own program                | [API overview](../api/overview.md), [Python usage](../reference/python.md)                                      |
| Write my own research tasks                          | [Existing development and execution guide](../dev_guide.md), [Plugin protocol](../reference/plugin-manifest.md) |

## What makes up the research process

| Stage    | Typical inputs                           | Typical results                                             |
| -------- | ---------------------------------------- | ----------------------------------------------------------- |
| Raw data | Tushare date range and dataset selection | Market and reference data as Parquet files in the workspace |
| ETL      | Raw data directory                       | Features, labels, and datasets reusable by later stages     |
| Analysis | ETL Task ID                              | Factor scores and analysis result files                     |
| Train    | ETL Task ID and model configuration      | Model, metrics, and optional training curves                |
| Predict  | Train Task ID                            | Offline prediction data and statistics                      |
| Backtest | Predict Task ID and strategy assumptions | Daily backtest, summaries, and position-related artifacts   |

The core framework provides basic Task contracts; research plugins implement the specific factors, models, and backtesting logic. The table describes a typical research chain. Actual inputs depend on the installed plugin's Task Schema. Analysis usually branches from ETL and does not have to run before Train.

Stages record upstream Task IDs through `source_tasks`, and results are saved in Task directories. You can reuse the same ETL results to train different models, or reuse predictions to compare different backtest parameters. The framework stores relationships for querying and display; users or calling programs organize the submission of each stage.

## Three entry points

**CLI** suits terminal operations and scripts. `axonx exec` runs a Task in the current process; `axonx submit` calls the service and delegates the task to an independent worker. Other Job commands query status, logs, machines, and the workspace.

**Studio** provides Task Schema forms, run details, machine resources, raw data, and research result pages. It sends requests to the same-origin backend, which forwards requests to the selected remote machine according to configuration.

**Agent** can use configured Job tools to query tasks, logs, files, and lineage, and explain research results based on evidence. The built-in Agent backend uses the Claude Agent SDK; external Agents can also call Jobs through the same service's MCP interface.

All three entry points share framework capabilities and workspace records. Their connections, authentication, and streaming response formats differ; see [Jobs and Tasks](../concepts/jobs-and-tasks.md), [Authentication](../guides/authentication.md), and [MCP integration](../agent/mcp-integration.md).

## Responsibilities

| Component                                       | Responsibilities                                                                    |
| ----------------------------------------------- | ----------------------------------------------------------------------------------- |
| Application, Component, Job, asynchronous Step  | Assemble infrastructure, validate call parameters, and execute interface operations |
| TaskManager, TaskRunner, synchronous Task steps | Start workers, perform computation, and publish status, progress, logs, and results |
| Research plugins                                | Implement data processing, factors, models, prediction, and backtesting algorithms  |
| Workspace                                       | Store task configuration, metadata, events, and artifacts                           |
| Studio                                          | Display tasks and research results through public interfaces and standard artifacts |
| Agent                                           | Assist with research and engineering within configured tools and SDK permissions    |

Process isolation makes it easier to run tasks separately, but is not a security sandbox. Machine resource pages provide monitoring; callers select remote targets. Check return definitions, cost assumptions, and trading constraints in the specific plugin; see [Interpreting backtests](../research/backtest.md).

## Next steps

For your first run, follow the [Quick start](quickstart.md) with the Demo, which requires no data or model credentials, to verify submission, waiting, and result retrieval before installing research plugins. If you already have a service, go directly to [Getting started with Studio](studio.md) or [Task management](../guides/task-management.md).

See [Architecture overview](../concepts/architecture.md) for the implementation structure; query the service's `/jobs` catalog for its current public capabilities.
