# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` adds two global factor families to the 158 Alpha158 inputs: cross-sectional return mean and variance over 1/3/5/10 trading days. ETL also publishes 5 stock-level momentum/risk columns: 13 optional columns and 171 features in total.

Training inherits cutoff-safe labels, early stopping on the final 10% of training dates and full-period refitting. Prediction and ordinary backtesting reuse the base plugin.

## Factors and timing

| Group    | Features | Definition                                                    |
| -------- | -------: | ------------------------------------------------------------- |
| mean     |        4 | Winsorized cross-sectional return mean: market direction      |
| variance |        4 | Winsorized cross-sectional sample variance: return dispersion |
| neutral  |        3 | Beta-adjusted momentum over 5/10/20 days                      |
| risk     |        2 | Residual volatility and downside risk over 20 days            |

Stock returns are adjusted C(T)/C(T−h)−1 for h=1/3/5/10 market trading days. Both endpoints must have quotes, positive volume, amount and adjusted prices. Price-limit stocks remain included; future labels and tradability are never consulted. For each date/horizon, winsorize at the linear 2%/98% quantiles, following Axon2's global feature implementation, then calculate the equal-weight mean and sample variance (ddof=1). Empty pools remain null; singleton variance is null. Variance measures cross-sectional disagreement; near-zero mean alone does not establish that most stocks are range-bound.

Features are available after T close and shared by every stock that day. Evaluate model ablations, since daily-constant factors have no cross-sectional IC. See [cross_section.py](axonx_qlib_factor/internal/cross_section.py); ETL saves daily values and horizon-specific pool counts.

`context_groups` accepts comma-separated `mean`, `variance`, `neutral`, `risk`, or `none`. The default remains `none` pending comparison. Compatibility change: the old `market/liquidity/relative/interaction` groups are retired. Old columns are excluded from new models and retired group configurations fail explicitly; historical tasks remain untouched. Rerun ETL for the new groups.

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
  --label-column label_return_rank --parameter-preset axonx --target http://research.example:1024
axonx submit --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --transaction-cost-rate 0.001 --target http://research.example:1024
```

Save each returned Task ID and Run ID and wait for `succeeded` before submitting downstream work. `qlib_factor_analysis` is an optional diagnostic branch. With the core from this checkout, Task-only wheel updates through the remote installation Job apply without restarting; restart when `restart_required` is true and verify Task definitions. Direct pip/source changes and older cores without plugin import refresh require restart. See [Qlib Alpha158](../qlib_a158/README.md) for source data, labels and execution assumptions.

<a id="experiments"></a>

## Final experiment settings and results

This section records this plugin’s final experiment. See the [three-layer comparison](../../docs/en/research/experiments.md#comparison) for cross-plugin results. Metrics come from successful machine-45 Tasks and their metadata, summary.parquet, daily.parquet and trades.parquet; original artifacts remain in the execution workspace.

### Detailed Setting

| Stage                 | Setting                                                                                                                                                                                                                                                                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data / universe       | Tushare adjusted prices and volumes; Shanghai/Shenzhen excluding Beijing, with no CSI300-only selection. ETL output 20150101–20261008: 11,446,950 rows and 5,477 stocks; Factor ETL publishes 171 features; the final risk model uses 160 columns. min_history_coverage=0.8; no forward-filling suspensions or missing quotes.                                  |
| Training dates        | `[20150101,20230101)`; both signal date and label_target_date precede the exclusive cutoff. Internal validation starts 20220316, using the last 10% of dates.                                                                                                                                                                                                   |
| Labels / filtering    | Adjusted signal-close to next-market-close returns; retain signal-date buyable rows with valid fixed-one-day labels available before cutoff. Trim 2.5% of raw returns at each daily tail; normalize average ranks to [0,1], singleton=0.5; transform fitting and validation samples separately. label_winsorize_tail=0.025; this experiment uses rank, not CSZ. |
| Sample counts         | 6,147,420 rows before trimming; full-period refit on 5,838,557 rows after trimming; tuning train 5,010,901 and validation 823,601 rows.                                                                                                                                                                                                                         |
| LightGBM              | 4.7.0, parameter_preset=axonx, objective=regression, metric=[l2,l1]; learning_rate=0.03, num_leaves=31, max_depth=-1, min_data_in_leaf=20, bagging_fraction=0.9, bagging_freq=1, lambda_l1=lambda_l2=0. feature_fraction=1.0.                                                                                                                                   |
| Rounds / refit        | num_boost_round=1000, early_stopping_rounds=50; validation L2 selects rounds before refitting all training samples. Training-validation RankIC selects the final risk model.                                                                                                                                                                                    |
| Determinism           | random_seed=42; LightGBM seed, feature_fraction_seed, bagging_seed and data_random_seed all 42; num_threads=8, deterministic=true, force_col_wise=true.                                                                                                                                                                                                         |
| Out of sample         | pred_start=20230101, pred_end=20261008; actual overall evaluation 20230103–20261008, 909 market dates. 2026 is incomplete.                                                                                                                                                                                                                                      |
| Portfolio / execution | Top20 primary, Top30 secondary; same-close quote proxy, sells before buys, price-limit and eligibility constraints. New entries receive at most 1/N equity; no replacement for unfilled entries, blocked exits retain capital, retained weights are not rebalanced. No forced final liquidation.                                                                |
| Fees / annualization  | transaction_cost_rate=0.001 on each executed side; buy_cost_rate=sell_cost_rate=null uses the shared rate, without a minimum fee. annualization_days=252, annual_risk_free_rate=0.012.                                                                                                                                                                          |
| Shared inputs         | This experiment uses the upstream ETL market.parquet, calendar.parquet and labels.parquet; as_of_date=20261008, index_codes=[], minimum_index_weight_coverage=0.98.                                                                                                                                                                                             |

The model uses 160 features and refits the full training period after early stopping selects 426 rounds. Validation RankIC is 0.11321.

stock_risk adds only `f_context_residual_vol20` and `f_context_downside_risk20`, without global moments or neutral columns. Its saved `context_windows=[10]` filters only global moments and therefore has no effect on risk features. Stock daily returns are clipped at contemporaneous cross-sectional 2%/98% linear quantiles; market return is the clipped equal-weight mean. Beta uses 60 market dates through T−1 with at least 30 valid paired returns, covariance/market variance, clipped to [−3,3]; market variance ≤1e−12 leaves beta undefined. Daily residual return is clipped stock return minus historical beta × market return. Residual volatility is its 20-day sample standard deviation (ddof=1); downside risk is sqrt(mean(min(clipped daily return,0)²)). Both require at least 16 valid observations in 20 dates; missing/undefined values remain missing.

context_groups=risk, context_windows=[10], fixed holding_days=1; the plugin default for context_groups remains none.

### Metric definitions

Overall IC/RankIC averages daily Pearson/Spearman correlations between predictions and valid next-day labels on signal-date eligible stocks, independently of holdings and TopN. Unannualized RankICIR = mean(daily RankIC)/std(daily RankIC,ddof=1); the annualized version multiplies by sqrt(252). Both are shown to distinguish backtest and factor-analysis conventions.

Net annualized = (∏(1+r_net))^(252/D)−1; net Sharpe = (mean(r_net)−[(1.012)^(1/252)−1])/std(r_net,ddof=1)×sqrt(252). Drawdown uses compounded net equity with initial equity 1 included in the running peak. Turnover = (executed buys+sells)/prior equity; full replacement is about 200%. Win rate is the share of positive net-return dates.

The universe-mean benchmark equally weights the full prediction cross-section with valid forward labels, not just Top20 and not the clipped mean used in risk features. HS300 is a constituent-weighted return proxy with at least 98% weight coverage, not the official CSI300 index quote series. Both benchmarks have 908 valid dates, 20230104–20261008. Net active metrics use this shared window; portfolio-only metrics use all 909 dates.

Net daily active return a_t = r_net,t−r_benchmark,t. **Net IR** = mean(a)/std(a,ddof=1)×sqrt(252). Net active annualized return compounds ∏(1+a) and annualizes over 908 dates; active drawdown uses the same compounded active-return curve. These are neither differences of annualized returns nor portfolio/benchmark equity ratios. Framework information_ratio fields use gross returns; this section recomputes net metrics from daily artifacts.

### Overall signals and full Top20 results

| Metric                                   | Factor: stock_risk |
| ---------------------------------------- | -----------------: |
| Overall IC                               |             0.0545 |
| Overall RankIC                           |             0.0966 |
| Overall RankICIR (annualized)            |            14.2859 |
| Overall RankICIR (unannualized)          |             0.8999 |
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
| Factor: stock_risk: backtest | `backtest#qlib_factor_backtest#2026100917v6ku` | `37cf5867c5d344da9c4b6a9b56bc6e24` |

| Input    | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

Core/plugin versions: 0.1.1 / 0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0. New data do not guarantee reproduction of the unpublished historical snapshot; raw artifacts are not committed.
