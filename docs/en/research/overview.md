# Quantitative Research

Implement quantitative logic in plugins, execute Tasks and retain evidence, then evaluate changes with consistent definitions. AxonX provides contracts and a runtime; plugins define algorithms and data requirements. Alpha158 is the reference workflow, and other methods can use the same plugin contracts.

## Choose a research step

| Goal                                 | Start here                                                                                          | Outcome                                                         |
| ------------------------------------ | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Have an Agent implement an objective | [Skill and research prompt](../agent/research-prompt.md)                                            | Define hypotheses, baseline, controls, and tools                |
| Run the Alpha158 baseline            | [Tushare data](tushare.md) → [Alpha158 workflow](workflow.md)                                       | Successful ETL → Train → Predict → Backtest records             |
| Develop or improve a plugin          | [Development and operations guide](../dev_guide.md) → [Plugin management](../plugins/management.md) | Implement, register, install, and discover Tasks                |
| Inspect execution artifacts          | [Reading results](results.md) → [Backtest methodology](backtest.md)                                 | Inspect features, models, predictions, and the portfolio ledger |
| Evaluate a research change           | [Strategy comparison](strategy-comparison.md) → [Experiment design](experiments.md)                 | Align definitions, control variables, and confirm independently |
| Reproduce a documented case          | [Alpha158 improvement case](alpha158-case.md)                                                       | Settings, metrics, commands, and Task/Run provenance            |

## Extend a baseline progressively

[Alpha158](../../../plugins/qlib_a158/README.md) provides 158 price/volume features, LightGBM, factor analysis, and TopN backtesting. [Qlib Factor](../../../plugins/qlib_factor/README.md) extends ETL and training with 13 optional features; training still defaults to the 158 baseline features. [Qlib Strategy](../../../plugins/qlib_strategy/README.md) reuses predictions and adds minimum holding periods, rank retention, and replacement count limits.

Plugin READMEs maintain parameters, algorithms, and artifact definitions. Discover the selected service's actual Task schemas and check upstream compatibility before submission. See [research artifact contracts](../reference/research-artifacts.md) for fields.

## Execution and conclusions

Keep source changes, service installation, and Task submission separate. Retain source revisions, data snapshots, windows, parameters, costs, and actual Task/Run IDs. Wait for upstream success before downstream submission; lineage records do not automatically schedule a DAG. Factor analysis branches independently from ETL and is not a training prerequisite.

Task success establishes completed execution. Algorithm improvement requires comparable settings, candidate selection records, and independent confirmation. The [Alpha158 case](alpha158-case.md) reports three fixed configurations with limits for incomplete data, parameter differences, and missing independent confirmation.
