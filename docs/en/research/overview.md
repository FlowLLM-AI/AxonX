# Quantitative research

Use AxonX to turn research steps into Tasks with explicit inputs, inspectable artifacts, and upstream relationships. Start with a working service and the [demo tutorial](../getting-started/quickstart.md). Research algorithms and data requirements belong to installed plugins.

## Choose the next step

| Goal                        | Guide                                         | Result                                                                |
| --------------------------- | --------------------------------------------- | --------------------------------------------------------------------- |
| Execute the Alpha158 chain  | [Research workflow](workflow.md)              | Successful ETL → Train → Predict → Backtest records                   |
| Prepare historical data     | [Tushare data](tushare.md)                    | Raw partitions and master data covering the experiment                |
| Inspect stage outputs       | [Reading results](results.md)                 | Feature, model, prediction, and backtest evidence                     |
| Evaluate a change           | [Experiment design](experiments.md)           | Controls, ablations, a locked candidate, and independent confirmation |
| Interpret portfolio metrics | [Backtest methodology](backtest.md)           | Returns, costs, drawdown, and execution assumptions                   |
| Compare two strategies      | [Strategy comparison](strategy-comparison.md) | Metrics over common valid dates                                       |

Factor analysis branches from ETL independently; it is not required before training. Submission returns a handle; wait for that execution to succeed before passing its Task ID downstream. Lineage records dependencies without automatically scheduling the chain.

## Choose a research plugin

[Plugin management](../plugins/management.md) explains installation and discovery in the execution environment. [Alpha158](../../../plugins/qlib_a158/README.md) provides the baseline price/volume features, LightGBM training, and TopN backtest. [Qlib Factor](../../../plugins/qlib_factor/README.md) adds independently registered Tasks and configurable feature groups.

Discover the installed Task schemas before submitting. Keep parameters, algorithms, and artifact definitions with the plugin; use [research artifact contracts](../reference/research-artifacts.md) when implementing outputs for Studio.

## Follow the agent-developed experiment

The [README benchmark](../../../README.md#benchmark-agent-developed-market-cross-sectional-features) shows final three-layer metrics. The [three-layer comparison](experiments.md#comparison) maintains shared settings, benchmark definitions and same-policy controls. Fees are 0.1% per side; the 10-day main policy earns 17.16%/18.60% annualized for Top20/Top30. Three days is exploratory. Each plugin README records only its own detailed settings and results.

Read [experiment design](experiments.md) for the reusable method and [external agents](../agent/external.md) for agent access.
