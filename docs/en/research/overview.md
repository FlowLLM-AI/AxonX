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

[Plugin management](../plugins/management.md) explains installation and discovery in the execution environment. [Alpha158](../../../plugins/a158/README.md) provides the baseline price/volume features, LightGBM training, and TopN backtest. [Alpha158 Enhanced](../../../plugins/a158_enhanced/README.md) adds independently registered Tasks and configurable feature groups.

Discover the installed Task schemas before submitting. Keep parameters, algorithms, and artifact definitions with the plugin; use [research artifact contracts](../reference/research-artifacts.md) when implementing outputs for Studio.

## Follow the agent-developed experiment

The [README benchmark](../../../README.md#benchmark-agent-developed-market-cross-sectional-features) follows Codex developing a separate plugin, running ablations, locking a configuration, and checking an independent period. Confirmation-period Top10 net annualized return rose from −5.74% to 28.21%, and Top20 from −3.24% to 24.93%.

Read [experiment design](experiments.md) for the reusable method and the plugin's [complete results](../../../plugins/a158_enhanced/EXPERIMENT_RESULTS.md) for recorded evidence. For agent access, continue with [external agents](../agent/external.md).
