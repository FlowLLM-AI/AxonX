# Qlib Strategy 实验结果

[English](EXPERIMENT_RESULTS.md) · [简体中文](EXPERIMENT_RESULTS_ZH.md)

2026-10-09 在 45 机器执行。训练 `[20150101,20230101)`，样本外预测与回测 `20230103–20261008`，909 个市场日。标签 rank、AxonX LightGBM 参数、种子 42、8 线程；买入 0.05% / 卖出 0.15%，252 日年化、无风险利率 1.2%，不强制期末平仓。

按训练期内部验证 RankIC 选择 `liquidity`，共 164 个模型特征。训练 5,838,557 行；选组不使用 2023 年后的收益。

主方案预先固定为最短持有 10 日、replacement_fraction=0.2、rank_buffer=1；同一基础/增强预测各跑 6 个持有期，合计 12 组。持有期对照不改变预设主方案。

## 全部持有期对照

| Model  | Minimum days | Top5   | Top10  | Top20  | Top30  |
| ------ | ------------ | ------ | ------ | ------ | ------ |
| base   | 0            | 17.28% | 14.67% | 21.57% | 23.65% |
| base   | 5            | 21.67% | 17.16% | 13.07% | 16.80% |
| base   | 10           | 15.37% | 27.54% | 18.70% | 22.59% |
| base   | 15           | -1.12% | -1.53% | 5.09%  | 7.56%  |
| base   | 20           | 8.96%  | 15.39% | 18.02% | 17.68% |
| base   | 30           | -1.10% | -0.27% | 5.11%  | 2.91%  |
| factor | 0            | 10.15% | 18.18% | 17.95% | 19.21% |
| factor | 5            | 11.40% | 21.24% | 15.88% | 18.98% |
| factor | 10           | 7.01%  | 20.85% | 19.35% | 15.72% |
| factor | 15           | 4.13%  | 9.90%  | 15.01% | 14.94% |
| factor | 20           | 20.38% | 15.02% | 21.59% | 23.75% |
| factor | 30           | 18.86% | 10.17% | 10.98% | 7.85%  |

## base 默认 10 日方案

| TopN | Net annualized | Net cumulative | Max drawdown | Net Sharpe | Turnover | Daily cost |
| ---- | -------------- | -------------- | ------------ | ---------- | -------- | ---------- |
| 5    | 15.37%         | 67.49%         | -40.00%      | 0.5654     | 19.64%   | 0.02%      |
| 10   | 27.54%         | 140.46%        | -31.12%      | 0.9491     | 19.77%   | 0.02%      |
| 20   | 18.70%         | 85.60%         | -32.24%      | 0.7417     | 19.77%   | 0.02%      |
| 30   | 22.59%         | 108.45%        | -31.95%      | 0.8880     | 19.78%   | 0.02%      |

## factor 默认 10 日方案

| TopN | Net annualized | Net cumulative | Max drawdown | Net Sharpe | Turnover | Daily cost |
| ---- | -------------- | -------------- | ------------ | ---------- | -------- | ---------- |
| 5    | 7.01%          | 27.70%         | -42.69%      | 0.3355     | 19.68%   | 0.02%      |
| 10   | 20.85%         | 98.03%         | -33.80%      | 0.7890     | 19.71%   | 0.02%      |
| 20   | 19.35%         | 89.31%         | -34.68%      | 0.7627     | 19.73%   | 0.02%      |
| 30   | 15.72%         | 69.33%         | -34.22%      | 0.6423     | 19.72%   | 0.02%      |

完整风险、成本、换手及 Task / Run ID 见 [policy_comparison.csv](experiments/policy_comparison.csv)，分年结果见 [yearly_comparison.csv](experiments/yearly_comparison.csv)。

## 执行与质量

基础与增强回测均使用相同的行情、标签和日历 SHA-256。每条实际订单的买入 0.05% / 卖出 0.15% 已核对，未成交收费为零。每日上限按成交股票数量计算，首次建仓豁免，保留仓位不再平衡。部分缺行情结果标记 `incomplete_market_data`。

## 任务来源

| Variant               | Task ID                                        | Run ID                           |
| --------------------- | ---------------------------------------------- | -------------------------------- |
| strategies/base_m0    | backtest#qlib_strategy_backtest#2026100914GIao | f4a3b5ba95e344a6b8b46cc0b95e4f2f |
| strategies/base_m10   | backtest#qlib_strategy_backtest#2026100914vKv8 | 3ade4691a5044a0eb87214733d746532 |
| strategies/base_m15   | backtest#qlib_strategy_backtest#20261009144L60 | b974ac23e390432681855318f3f6a085 |
| strategies/base_m20   | backtest#qlib_strategy_backtest#2026100914Dl72 | 7a98ed0848924110893f4a52c255564d |
| strategies/base_m30   | backtest#qlib_strategy_backtest#2026100914kWd9 | 29226dab736048a9ad2940ffaac848d0 |
| strategies/base_m5    | backtest#qlib_strategy_backtest#2026100914YMdR | f8e289ac01044120bfbdb5d3faae92e1 |
| strategies/factor_m0  | backtest#qlib_strategy_backtest#20261009147qyv | a98a742c98774d6abfb5aebd61ecc34e |
| strategies/factor_m10 | backtest#qlib_strategy_backtest#2026100914NUkh | 5418fa3883c6463dbc4f07af4c23ed94 |
| strategies/factor_m15 | backtest#qlib_strategy_backtest#2026100914l310 | c4e6298d96f548c18660a0388ca9989e |
| strategies/factor_m20 | backtest#qlib_strategy_backtest#2026100914dD1D | b26f8010875c49f1b40f4938d05e6dba |
| strategies/factor_m30 | backtest#qlib_strategy_backtest#20261009146kXv | ac56687b75484b37b54fb0c0e238b1f7 |
| strategies/factor_m5  | backtest#qlib_strategy_backtest#2026100914CeJS | 6390deb19d014a56a69eb96d3027c0be |
