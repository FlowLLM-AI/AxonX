# 当前策略指标

[English](README.md) · [简体中文](README_ZH.md)

- [policy_comparison.csv](policy_comparison.csv)：基础与因子预测 × 六种最短持有期 × Top5/10/20/30，包含风险、换手、成本及实际 Task / Run ID。
- [yearly_comparison.csv](yearly_comparison.csv)：各模型、持有期和 TopN 的分年指标。

主要策略预先设定为最短持有 10 天、`replacement_fraction=0.2`、`rank_buffer=1`。全部结果使用 0.05% 买入费率和 0.15% 卖出费率。这些精简汇总随仓库提供，完整日级产物保留在远程 Task 中，其他实验窗口见[历史归档](../archives/20261009/)。
