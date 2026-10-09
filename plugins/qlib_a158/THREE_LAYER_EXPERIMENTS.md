# Qlib three-layer experiment

[English](THREE_LAYER_EXPERIMENTS.md) · [简体中文](THREE_LAYER_EXPERIMENTS_ZH.md)

Executed on machine 45 on 2026-10-09. Training: `[20150101,20230101)`. OOS prediction/backtesting: `20230103–20261008`, 909 market dates. Rank labels, AxonX LightGBM parameters, seed 42 and 8 threads. Fees: 0.05% buy / 0.15% sell; 252-day annualization, 1.2% risk-free rate and no forced final liquidation.

Training-period validation RankIC selects `liquidity` with 164 model features. Training uses 5,838,557 rows; post-2022 returns do not select the groups.

The primary strategy is fixed at a 10-day minimum, a 20% daily count cap per side and rank buffer 1. Base and factor layers use fixed one-day holding backtests.

## Net annualized returns

| Scheme        | Top5   | Top10  | Top20  | Top30  |
| ------------- | ------ | ------ | ------ | ------ |
| qlib_a158     | 23.42% | 14.00% | 7.67%  | 0.97%  |
| qlib_factor   | 8.86%  | -5.33% | -1.83% | -1.58% |
| qlib_strategy | 7.01%  | 20.85% | 19.35% | 15.72% |
| base + policy | 15.37% | 27.54% | 18.70% | 22.59% |

Mean two-sided turnover is about 199.2% for the factor model and 19.7% for the policy, with daily costs decreasing from about 0.20% to 0.02%. The same policy on base predictions returns 22.59% net annualized at Top30, above the factor prediction result of 15.72%; factor gains do not hold across all portfolio sizes.

## Top20 / Top30 risk and turnover

| Scheme        | TopN | Max drawdown | Net Sharpe | Turnover | Daily cost |
| ------------- | ---- | ------------ | ---------- | -------- | ---------- |
| qlib_a158     | 20   | -38.65%      | 0.3619     | 198.83%  | 0.20%      |
| qlib_a158     | 30   | -40.60%      | 0.1308     | 199.02%  | 0.20%      |
| qlib_factor   | 20   | -35.35%      | 0.0368     | 199.20%  | 0.20%      |
| qlib_factor   | 30   | -34.34%      | 0.0409     | 199.18%  | 0.20%      |
| qlib_strategy | 20   | -34.68%      | 0.7627     | 19.73%   | 0.02%      |
| qlib_strategy | 30   | -34.22%      | 0.6423     | 19.72%   | 0.02%      |
| base + policy | 20   | -32.24%      | 0.7417     | 19.77%   | 0.02%      |
| base + policy | 30   | -31.95%      | 0.8880     | 19.78%   | 0.02%      |

## Controls and provenance

All 175 shared base/factor ETL columns match, with 26 additions. The none model reproduces the full base predictions. Every backtest reuses identical market, labels and calendar files, with fees and unfilled orders checked. All 16 factor combinations and 12 policy candidates succeeded. OOS returns select neither the factor groups nor the primary policy.

[All factor results](../qlib_factor/EXPERIMENT_RESULTS.md) · [All policy results](../qlib_strategy/EXPERIMENT_RESULTS.md). The reports and experiments directories record Task / Run IDs, settings and candidate summaries.

Results include missing quotes and report `incomplete_market_data`; 2026 ends on October 8. Same-close quotes proxy fills, and normalized cash omits the RMB 5 minimum fee.

## Software provenance

- `axonx-qlib-a158` 0.2.0; content SHA-256 `9745ba0b80d213e9712fcf36b4cafd798ce100574401ece5031adc5323c042de`.
- `axonx-qlib-factor` 0.2.0; content SHA-256 `921b54768ffdcb2208627a67a5d9210e77b400b89cb36b70d54dc75f26c113a9`.
- `axonx-qlib-strategy` 0.2.0; content SHA-256 `86b7d6dc2b3712be65902bfbf7b32fd2422fbdd92083e34aaf5b7e210c6be985`.

See [archives](archives/20261009/THREE_LAYER_EXPERIMENTS.md) for other experiment settings.
