# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` extends Alpha158 ETL with 13 optional market-moment, neutral-momentum and risk features, producing 171 feature columns. Training selects groups; the default empty group list uses the 158 base features. The example below selects `risk` (160 features).

Training inherits cutoff-safe labels, early stopping on the final 10% of training dates and full-period refitting. Prediction and ordinary backtesting reuse the base plugin.

## Factors and timing

| Group    | Features | Definition                                                    |
| -------- | -------: | ------------------------------------------------------------- |
| mean     |        4 | Winsorized cross-sectional return mean: market direction      |
| variance |        4 | Winsorized cross-sectional sample variance: return dispersion |
| neutral  |        3 | Beta-adjusted momentum over 5/10/20 days                      |
| risk     |        2 | Residual volatility and downside risk over 20 days            |

Stock returns are adjusted C(T)/C(T−h)−1 for h=1/3/5/10 market trading days. Both endpoints must have quotes, positive volume, amount and adjusted prices. Price-limit stocks remain included; future labels and tradability are never consulted. For each date/horizon, winsorize at the linear 2%/98% quantiles, then calculate the equal-weight mean and sample variance (ddof=1). Empty pools remain null; singleton variance is null. Variance measures cross-sectional disagreement; near-zero mean alone does not establish that most stocks are range-bound.

Global moments are available after T close and shared by every stock that day; momentum/risk features vary by stock. Evaluate model ablations, since daily-constant factors have no cross-sectional IC. See [features.py](axonx_qlib_factor/features.py); ETL saves daily values and horizon-specific pool counts.

`context_groups` is a list selected from `mean`, `variance`, `neutral` and `risk`. The default `[]` uses only the 158 base features; the example selects `["risk"]`. Unsupported groups and context columns fail validation.

`context_windows` selects a nonempty subset of `[1,3,5,10]`, defaulting to all four horizons. ETL publishes all 13 factors; context_windows filters only global mean/variance, while stock groups retain their fixed windows. Ablations reuse that dataset, and training metadata records the selected windows. For example, `--context-groups '["mean","variance"]' --context-windows '[10]'` adds only two 10-day factors.

Beta uses the preceding 60 market dates through T−1, with at least 30 paired stock/market returns. Stock daily returns use contemporaneous 2%/98% winsorization; the market return is their equal-weight mean. Beta is covariance divided by market variance, clipped to [−3,3]; variance ≤1e−12 leaves it undefined. Neutral momentum subtracts prior beta times compounded market returns from the stock's 5/10/20-day return. Residual volatility is the 20-day sample standard deviation of stock return minus prior beta × market return; downside risk is sqrt(mean(min(stock return,0)²)). Both risk windows require 16 valid observations out of 20. All stock features remain null when the current quote is invalid.

ETL reads 80 market dates before the requested output start so each residual in the 20-day risk window has its preceding 60-day beta history. The signal-eligibility history requirement remains 60 dates. With sufficient source history, overlapping features are independent of the requested output start.

Plugin version 0.3.0 requires Python 3.12+, AxonX `>=0.3.0` and upstream research plugins `>=0.3.0`. Install the layers in dependency order. Research artifacts use protocol v1.

## Install and run

Research plugins are not published to PyPI. Clone the repository and install the AxonX 0.3.0 core (`pip install -e .` from its root); run the following commands from its root. For local Agent development, install in dependency order in the execution service's Python environment:

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
```

For remote installation and service refresh, follow [plugin management](../../docs/en/plugins/management.md). The examples below require installed plugins/data, `AXONX_TARGET_TOKEN`, and your service address in place of `http://research.example:1024`.

```bash
axonx get_task_def --task qlib_factor_train --target http://research.example:1024

axonx exec --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_train --upstream-task-ids '["<etl_task_id>"]' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx \
  --context-groups '["risk"]' --feature-fraction 1.0 --target http://research.example:1024
axonx exec --task qlib_a158_predict --upstream-task-ids '["<train_task_id>"]' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<predict_task_id>"]' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Record each Task ID and `started_at` from execution logs or `status --detail full`; continue only after a zero exit code and `succeeded` state. `qlib_a158_analysis` analyzes the factor ETL as an optional diagnostic branch. Installation modifies the selected interpreter. New CLI processes discover installed plugins; definition Jobs and Studio retain the service startup catalog until restart. Stop on installation or verification failures. [Qlib Alpha158](../qlib_a158/README.md)

## Execution and configuration

Use `axonx app` with the standard application configuration. This plugin registers `qlib_factor_etl` and `qlib_factor_train`; reuse `qlib_a158_analysis`, `qlib_a158_predict` and `qlib_a158_backtest` for the other stages. Supply dates, feature groups and model settings to each Task. Prediction accepts a Train and an optional compatible ETL to score new data.

## Local validation

From the repository root, with all three research plugins and development dependencies installed:

```bash
python -m pytest plugins/qlib_factor/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

The research tests execute the factor and strategy chains against temporary synthetic market data, including artifact exchange and explicit prediction ETL selection.

## Experiments

Shared settings, results, reproduction commands and Task provenance are maintained in the [Alpha158 improvement case](../../docs/en/research/alpha158-case.md). Artifact fields and universe reports follow the [shared protocol](../../docs/en/reference/research-artifacts.md).
