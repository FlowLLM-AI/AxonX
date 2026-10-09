# Alpha158 three-layer experiment: final record

[English](THREE_LAYER_EXPERIMENTS.md) · [简体中文](THREE_LAYER_EXPERIMENTS_ZH.md)

Train on 2015–2022; predict and backtest the complete 20230103–20261008 interval: 909 market days. Reuse the completed baseline; submit new experiments to `research.example:1024` following the [development guide](../../docs/en/dev_guide.md). Charge 0.2% per executed side, annualize over 252 days with a 1.2% risk-free rate, use closing-quote execution and do not force liquidation at cutoff.

## Net annualized returns

| Scheme                              | Top5    | Top10   | Top20   | Top30   |
| ----------------------------------- | ------- | ------- | ------- | ------- |
| a158: ordinary                      | -30.49% | -32.23% | -36.46% | -38.62% |
| a158_factor: 179 features           | -29.83% | -24.37% | -32.17% | -35.59% |
| a158_strategy: daily ≤20% + 10 days | 32.60%  | 25.27%  | 27.59%  | 22.14%  |

Net annualized return increases across all three layers for each reported N in this experiment. The factor layer remains negative; the policy layer turns positive. The tables below retain the key results; factor and policy comparison CSVs retain the selection metrics.

## Layer two: factor selection

ETL retains 158 base features and the existing 26 context factors. Test all 15 nonempty group combinations plus a no-context control, varying only context_groups with identical training settings and samples. Select by mean Top20/Top30 net annualized return. The shared scheme is `market,liquidity,interaction`: 179 model features, 5,838,557 training rows, 317 refit rounds and training-validation RankIC 0.10978.

The shared scheme also wins Top20 (−32.17%). The individual Top30 winner is `interaction` (−34.98%). The main comparison uses one shared model; see [all group metrics](../a158_factor/experiments/factor_comparison.csv).

## Layer three: portfolio selection

Reuse the selected factor model and predictions. Compare minimum holding periods of 0, 5, 10, 15, 20 and 30 days, with each side replacing at most floor(N × 20%) stocks daily, except initial entry. The same mean-return rule selects 10 days. Retain TopN holdings; after the minimum period, exit the worst ranks outside TopN. A count cap is not a notional cap; retained weights drift without rebalancing.

| TopN | Net annualized | Max drawdown | Net Sharpe | Mean two-sided turnover |
| ---- | -------------- | ------------ | ---------- | ----------------------- |
| 20   | 27.59%         | -33.01%      | 0.984      | 19.78%                  |
| 30   | 22.14%         | -32.22%      | 0.836      | 19.77%                  |

For Top30 alone, the 20-day minimum wins at +24.98%; the shared default remains 10 days. See [all six policy results](../a158_strategy/experiments/policy_comparison.csv).

## Tasks and quality

| Layer/stage            | Task ID                                  | Run ID                             |
| ---------------------- | ---------------------------------------- | ---------------------------------- |
| a158 etl               | `etl#a158_etl#20261009009auu`            | `296aff8be8fe442a92ec2183c79457be` |
| a158 train             | `train#a158_train#2026100900kEFu`        | `4bab10afe0ba4e68b04abf96e6f7f030` |
| a158 predict           | `predict#a158_predict#2026100900xoYQ`    | `19a3d34ba1ae42d48d990bc8b4858a2f` |
| a158 backtest          | `backtest#a158_backtest#2026100900tkX4`  | `4e4f15d386e64d02a0f8e62a396f0099` |
| a158_factor etl        | `etl#a158f_etl#2026100902ERpD`           | `2c414efff7924a788530b4f17698ab1d` |
| a158_factor train      | `train#a158f_train#2026100902qtld`       | `c2034731eeca4a748e1e5565271bb857` |
| a158_factor predict    | `predict#a158f_predict#2026100902cj1B`   | `889d4911c61f42038504e93ad289025d` |
| a158_factor backtest   | `backtest#a158f_backtest#2026100902BvnZ` | `40593cccceb248378ed7b13c6c155b70` |
| a158_strategy backtest | `backtest#a158s_backtest#20261009027CnU` | `c99ab46fba7144478df9ac7c357b759a` |

All 11,446,950 rows and 175 shared base columns match by value. Market, labels and calendar match by value; market Parquet byte digests differ. The no-context baseline replay and registered-policy replay against the independent prototype both have zero daily error. All six selected-model policies use identical input digests; filled-order caps, cash plus positions equals equity, and daily order fees reconcile.

All results are provisional (`incomplete_market_data`): missing quotes carry stale marks and block exits. The complete post-2022 interval was used to select groups and holding periods, creating selection bias; this is neither independent validation nor realized live-trading performance.

The repository retains this report and compact factor/policy comparison metrics. Generated daily data, compressed backtest outputs and run manifests are excluded. New runs should save their own provenance and artifacts.
