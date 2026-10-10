# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` extends Alpha158 ETL with 13 optional market-moment, neutral-momentum and risk features, producing 171 feature columns. Training selects groups; the default `none` uses the 158 base features. The example below selects `risk` (160 features).

Training inherits cutoff-safe labels, early stopping on the final 10% of training dates and full-period refitting. Prediction and ordinary backtesting reuse the base plugin.

## Factors and timing

| Group    | Features | Definition                                                    |
| -------- | -------: | ------------------------------------------------------------- |
| mean     |        4 | Winsorized cross-sectional return mean: market direction      |
| variance |        4 | Winsorized cross-sectional sample variance: return dispersion |
| neutral  |        3 | Beta-adjusted momentum over 5/10/20 days                      |
| risk     |        2 | Residual volatility and downside risk over 20 days            |

Stock returns are adjusted C(T)/C(T−h)−1 for h=1/3/5/10 market trading days. Both endpoints must have quotes, positive volume, amount and adjusted prices. Price-limit stocks remain included; future labels and tradability are never consulted. For each date/horizon, winsorize at the linear 2%/98% quantiles, following Axon2's global feature implementation, then calculate the equal-weight mean and sample variance (ddof=1). Empty pools remain null; singleton variance is null. Variance measures cross-sectional disagreement; near-zero mean alone does not establish that most stocks are range-bound.

Global moments are available after T close and shared by every stock that day; momentum/risk features vary by stock. Evaluate model ablations, since daily-constant factors have no cross-sectional IC. See [cross_section.py](axonx_qlib_factor/internal/cross_section.py); ETL saves daily values and horizon-specific pool counts.

`context_groups` accepts comma-separated `mean`, `variance`, `neutral`, `risk`, or `none`. The default remains `none`; the documented factor version explicitly uses `risk`. Unsupported groups and context columns fail validation.

`context_windows` selects a nonempty subset of `[1,3,5,10]`, defaulting to all four horizons. ETL publishes all 13 factors; context_windows filters only global mean/variance, while stock groups retain their fixed windows. Ablations reuse that dataset, and training metadata records the selected windows. For example, `--context-groups mean,variance --context-windows '[10]'` adds only two 10-day factors.

Beta uses the preceding 60 market dates through T−1, with at least 30 paired stock/market returns. Stock daily returns use contemporaneous 2%/98% winsorization; the market return is their equal-weight mean. Beta is covariance divided by market variance, clipped to [−3,3]; variance ≤1e−12 leaves it undefined. Neutral momentum subtracts prior beta times compounded market returns from the stock's 5/10/20-day return. Residual volatility is the 20-day sample standard deviation of stock return minus prior beta × market return; downside risk is sqrt(mean(min(stock return,0)²)). Both risk windows require 16 valid observations out of 20. All stock features remain null when the current quote is invalid.

## Install and run

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx get_task_definition --task qlib_factor_train --target http://research.example:1024

axonx submit --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx \
  --context-groups risk --feature-fraction 1.0 --target http://research.example:1024
axonx submit --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Save each returned Task ID and Run ID and wait for `succeeded` before submitting downstream work. `qlib_factor_analysis` is an optional diagnostic branch. Task-only wheel updates through the remote installation Job apply without restarting; restart when `restart_required` is true and verify Task definitions. Direct pip/source changes require restart. See [Qlib Alpha158](../qlib_a158/README.md) for source data, labels and execution assumptions.

## Recorded experiments

Settings, full results and artifact provenance are maintained in the [research experiment guide](../../docs/en/research/experiments.md#comparison). Historical records have not been rerun against the current code.
