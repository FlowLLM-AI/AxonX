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

[Plugin management](../plugins/management.md) explains installation and discovery in the execution environment. [Alpha158](../../../plugins/qlib_a158/README.md) provides the baseline price/volume features, LightGBM training, and TopN backtest. [Qlib Factor](../../../plugins/qlib_factor/README.md) adds independently registered Tasks and configurable feature groups. [Qlib Strategy](../../../plugins/qlib_strategy/README.md) reuses predictions and adds rank-retention portfolio management.

Discover the installed Task schemas before submitting. Keep parameters, algorithms, and artifact definitions with the plugin; use [research artifact contracts](../reference/research-artifacts.md) when implementing outputs for Studio.

## Follow the agent-developed experiment

The [README benchmark](../../../README.md#benchmark-agent-developed-market-cross-sectional-features) presents three versions corresponding to three plugins: Alpha158, two added risk factors, and a 3-day rank-retention policy. Shared settings, full metrics, and selection evidence live in the [experiment comparison](experiments.md#comparison); plugin READMEs maintain algorithms, configuration differences, and results. The policy was selected exploratorily and has not been independently confirmed.

Read [experiment design](experiments.md) for the reusable method and [external agents](../agent/external.md) for agent access.
