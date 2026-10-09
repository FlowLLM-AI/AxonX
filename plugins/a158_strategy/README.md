# Alpha158 Strategy

[English](README.md) · [简体中文](README_ZH.md)

`a158_strategy` inherits `a158_factor` and therefore `a158`, reusing factors, models and predictions while changing portfolio decisions. The framework owns valuation, cash, fees, orders, positions and trades.

## Simple policy

- Retain holdings that remain in TopN.
- After at least 10 market days, sell the worst-ranked holdings outside TopN first.
- Each day, each side fills at most `max(1, floor(N × 20%))` stocks: 1/2/4/6 for Top5/10/20/30. Initial entry is exempt. This count cap does not constrain notional when retained weights drift.
- Missing quotes or unsellable holdings retain capital. Sell before buying; failed entries receive no replacement. New entries receive at most 1/N equity; retained positions are not rebalanced. No forced liquidation at cutoff.

Parameters: `replacement_fraction=0.2`, `minimum_holding_days=10`, `rank_buffer=1`. Fixed expiry is disabled and `holding_days` must equal 1. `planned_exit_date` is null and `exit_delayed` does not measure rank-exit delays.

## Submission

Install requires the framework `portfolio_policy` extension. Deploy the current source, then run:

```bash
axonx plugin install plugins/a158_strategy --target http://research.example:1024
axonx submit --task a158s_backtest --source-tasks '<factor_predict_task_id>' --top-ns '[5,10,20,30]' --as-of-date 20261008 --target http://research.example:1024
```

`a158s_etl`, `a158s_factor`, `a158s_train` and `a158s_predict` register the factor-layer implementations. Reuse successful factor predictions when comparing policies, avoiding unnecessary retraining. Settings, Task/Run IDs, inputs and results are recorded in the [three-layer experiment](../a158/THREE_LAYER_EXPERIMENTS.md).

The policy came from a 150-policy exploratory sweep on baseline predictions, which is not independent validation. Missing quotes carry stale marks; `incomplete_market_data` results are provisional.
