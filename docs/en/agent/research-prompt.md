# Skill and Research Prompt

The AxonX Skill explains plugin authoring, Task contracts, execution, and evidence inspection; your research prompt defines the question to explore. Complete the [quickstart](../getting-started/quickstart.md), then choose an external or built-in Agent in the [development overview](overview.md).

## Prepare the development environment

1. Provide an AxonX source checkout and the plugin to change. A package installation alone does not include example plugin sources.
2. Ask the Agent to read the [AxonX Skill](../../../skills/axonx/SKILL.md), or install it using the host's supported mechanism. The built-in Agent can also load the bundled [development and operations guide](../dev_guide.md).
3. Supply file and command tools with source access. Configure the built-in Agent's `cwd`, SDK tools, and guide loading separately; see [configuration](configuration.md).
4. Select an execution service and prepare its plugins, dependencies, and data. Keep the same target for installation, submission, waiting, and queries.

External hosts configure their own models; the service configures the built-in model. Configure the AxonX service token and model credentials separately.

## Define the research objective

| Condition              | Include in the prompt                                                                             |
| ---------------------- | ------------------------------------------------------------------------------------------------- |
| Baseline and change    | Which plugin to use, and whether to create a plugin or improve an implementation                  |
| Hypothesis and goal    | Runtime efficiency, signal quality, or trading performance                                        |
| Data and timing        | Data snapshot, universe, history, and signal availability                                         |
| Windows and selection  | Training, validation, development, and independent confirmation windows; candidate selection rule |
| Evaluation             | Metrics, Top N, costs, fills, and exit assumptions                                                |
| Execution and delivery | Target service, source revision, Task/Run IDs, and artifacts                                      |

## A ready-to-use example

```text
Read the AxonX Skill and qlib_a158 source. Develop a separate research plugin
to investigate whether residual volatility and downside risk improve Alpha158 ranking.

Use only information available at signal time. Fix the data snapshot, labels,
sample filters, training parameters, windows, and costs for feature comparisons.
First specify development and independent confirmation windows and the candidate
selection rule; identify missing prerequisites before execution.

Implement and test the quantitative code, register the plugin, then install it
in the selected execution service. Discover that service's actual Task schemas,
check upstream compatibility, and run ETL, training, prediction, and backtesting,
waiting for each upstream execution to succeed.

Keep the source revision, data settings, parameters, costs, and actual Task/Run IDs.
Report RankIC, net returns, drawdown, turnover, failures, and evidence limits.
Lock the candidate before independent confirmation and propose the next change
based on the evidence.
```

You can instead specify training performance or portfolio policy improvements. Feature changes usually rerun the complete chain; model changes can reuse compatible ETL; portfolio changes can reuse compatible predictions. Reuse depends on actual Task schemas, fields, feature order, and artifact protocols.

## Complete a research loop

Keep source changes, execution-service installation, and Task submission separate. Passing code checks verifies implementation; research metrics and independent confirmation determine whether improvement claims are supported. Task success establishes completed execution.

See the [development and operations guide](../dev_guide.md) for implementation, [Alpha158 workflow](../research/workflow.md) for stage commands, [experiment design](../research/experiments.md) for comparisons, and the [Alpha158 case study](../research/alpha158-case.md) for a complete example.
