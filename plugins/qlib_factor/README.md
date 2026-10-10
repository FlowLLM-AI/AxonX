# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` adds two stock-level risk factors to the 158 Alpha158 inputs in the main experiment: 20-day residual volatility and downside risk, for 160 training features. ETL also publishes optional global mean, variance, and neutral momentum factors, for 171 columns in total. Reproduction commands here select only the `risk` group.

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

See the [detailed experiment settings](#experiments) below for stock momentum/risk calculation requirements and the final risk experiment.

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
  --transaction-cost-rate 0.001 --target http://research.example:1024
```

Save each returned Task ID and Run ID and wait for `succeeded` before submitting downstream work. `qlib_factor_analysis` is an optional diagnostic branch. Task-only wheel updates through the remote installation Job apply without restarting; restart when `restart_required` is true and verify Task definitions. Direct pip/source changes require restart. See [Qlib Alpha158](../qlib_a158/README.md) for source data, labels and execution assumptions.

<a id="experiments"></a>

## Final experiment settings and results

This section records this plugin’s final experiment. See the [three-version comparison](../../docs/en/research/experiments.md#comparison) for cross-plugin results. Metrics come from successful machine-45 Tasks and their metadata, summary.parquet, daily.parquet and trades.parquet; original artifacts remain in the execution workspace.

### Version configuration

158 base features plus two risk factors; context_groups=risk, feature_fraction=1.0; fixed holding_days=1.

Data, training windows, filtering, execution, and fee settings are maintained in the [three-version comparison](../../docs/en/research/experiments.md#comparison).

The model uses 160 features and refits the full training period after early stopping selects 426 rounds. Validation RankIC is 0.11321.

stock_risk adds only `f_context_residual_vol20` and `f_context_downside_risk20`, without global moments or neutral columns. Its saved `context_windows=[10]` filters only global moments and therefore has no effect on risk features. Stock daily returns are clipped at contemporaneous cross-sectional 2%/98% linear quantiles; market return is the clipped equal-weight mean. Beta uses 60 market dates through T−1 with at least 30 valid paired returns, covariance/market variance, clipped to [−3,3]; market variance ≤1e−12 leaves beta undefined. Daily residual return is clipped stock return minus historical beta × market return. Residual volatility is its 20-day sample standard deviation (ddof=1); downside risk is sqrt(mean(min(clipped daily return,0)²)). Both require at least 16 valid observations in 20 dates; missing/undefined values remain missing.

context_groups=risk, context_windows=[10], fixed holding_days=1; the plugin default for context_groups remains none.

### Metric definitions

Shared definitions for IC/RankIC, net returns, Sharpe, turnover, and active metrics are maintained in the [experiment comparison](../../docs/en/research/experiments.md#comparison). Portfolio metrics use 909 dates; active metrics use 908 benchmark-valid dates.

### Overall signals and full Top20 results

| Metric                                   | Factor: stock_risk |
| ---------------------------------------- | -----------------: |
| Overall IC                               |             0.0545 |
| Overall RankIC                           |             0.0966 |
| Overall RankICIR (annualized)            |            14.2859 |
| Net annualized                           |              9.04% |
| Net cumulative return                    |             36.64% |
| Net Sharpe                               |             0.4054 |
| Net annualized volatility                |             28.53% |
| Max drawdown                             |            -40.67% |
| Daily return win rate                    |             53.47% |
| Mean daily two-sided turnover            |            199.35% |
| Mean daily cost / prior equity           |            0.1993% |
| Closed trades                            |             18,079 |
| Net active annualized vs universe mean   |             -1.86% |
| Net IR vs universe mean                  |            -0.0649 |
| Net active max drawdown vs universe mean |            -21.71% |
| Net active annualized vs HS300 proxy     |              4.09% |
| Net IR vs HS300 proxy                    |             0.2947 |
| Net active max drawdown vs HS300 proxy   |            -29.34% |

### Top30 results

| Scheme             | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| ------------------ | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Factor: stock_risk |          4.27% |     0.2480 |      -41.41% |  199.37% |          -0.4236 |        0.0840 |

### Top20 yearly results

| Year | Days | Factor: stock_risk |
| ---- | ---: | -----------------: |
| 2023 |  242 |            -10.08% |
| 2024 |  242 |             10.54% |
| 2025 |  243 |             56.68% |
| 2026 |  182 |            -14.73% |

Yearly values are interval net annualized returns; 2026 ends October 8. Results report `incomplete_market_data`: missing quotes may delay exits and carry stale marks. Same-close fills are a proxy.

### Reproduce the experiment

Save Task/Run IDs and wait for success before each downstream submission; use the same `--target` for remote commands. Parameters below match the Setting table; verify remaining defaults with `get_task_definition` before submission.

```bash
axonx submit --task qlib_factor_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_factor_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 1.0 \
  --random-seed 42 --num-threads 8 \
  --context-groups risk --context-windows '[10]'
axonx submit --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008
axonx submit --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<market_path>' --calendar-file '<calendar_path>' --labels-file '<labels_path>'
```

### Task provenance and input checks

Execution workspace: `/nas/jinli.yl/data/axon` on machine 45.

| Stage / scheme               | Task ID                                        | Run ID                             |
| ---------------------------- | ---------------------------------------------- | ---------------------------------- |
| stock_risk: train            | `train#qlib_factor_train#2026100917VGxi`       | `d55e035ab9c549ab840770b1e8444f10` |
| stock_risk: predict          | `predict#qlib_factor_predict#2026100917Z7Ys`   | `1a033666806b4e359c6acc11f8b02399` |
| Factor: stock_risk: backtest | `backtest#qlib_factor_backtest#2026100917v6ku` | `37cf5867c5d344da9c4b6a9b56bc6e24` |

| Input    | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

Core/plugin versions: 0.1.1 / 0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0. New data do not guarantee reproduction of the unpublished historical snapshot; raw artifacts are not committed.
