# 实验汇总材料

本目录随仓库提交小体积、可阅读的结果与校验汇总。完整实验说明见上级目录的[计划](../DEVELOPMENT_PLAN.md)、[过程](../EXPERIMENT_PROCESS.md)和[结果](../EXPERIMENT_RESULTS.md)。

| 材料                                                               | 内容                                    |
| ------------------------------------------------------------------ | --------------------------------------- |
| [factor_comparison.csv](factor_comparison.csv)                     | 20261009 全部因子组合的四个 TopN 比较   |
| [selection_metrics.json](selection_metrics.json)                   | 2023–2024筛选期四个方案的主要指标       |
| [selection_decision.json](selection_decision.json)                 | 固定选择规则及锁定方案                  |
| [confirmation_metrics.json](confirmation_metrics.json)             | 2025–2026确认期基线和锁定方案的主要指标 |
| [paired_diagnostics.csv](paired_diagnostics.csv)                   | 同日差异及20交易日区块bootstrap区间     |
| [regime_metrics.csv](regime_metrics.csv)                           | 信号日市场涨跌环境下的RankIC和NDCG      |
| [selected_feature_importance.csv](selected_feature_importance.csv) | 选定模型的特征gain与split次数           |
| [baseline_data_parity.json](baseline_data_parity.json)             | 原始数据逐值对照结果                    |
| [training_parameters.json](training_parameters.json)               | 基线与增强方案共用训练配置及对照结果    |
| [context_feature_coverage.csv](context_feature_coverage.csv)       | 26个新增特征的有限值、NaN和Inf覆盖率    |

原始Task/Run响应、日志、日级Parquet和作废运行保留在实验执行者的本地归档中，由插件目录的 `.gitignore` 排除。绑定本次目标机器和已有任务的 `scripts/research.py`、`scripts/report.py` 同样仅供本地恢复执行，不随仓库提交。新实验应按计划重新选择目标服务、生成新的任务并保存独立记录。
