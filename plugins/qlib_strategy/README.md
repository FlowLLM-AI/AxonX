# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` inherits `qlib_factor` and `qlib_a158` to study portfolio policies using fixed predictions. The shared framework owns quotes, price limits, valuation, cash, side fees, orders, positions and trades.

## Rank-retention policy

- Retain holdings inside the current eligible TopN.
- After `minimum_holding_days` elapsed market dates, exit the worst-ranked holdings outside the buffered rank threshold first.
- Cap fills per side per day at `max(1,floor(N × replacement_fraction))`; initial construction is exempt.
- Blocked exits retain capital. Unfilled entries are not replaced, and sells precede buys. New positions receive at most 1/N equity; retained holdings are not rebalanced.

Defaults: `minimum_holding_days=10`, `replacement_fraction=0.2`, `rank_buffer=1`. Top5/10/20/30 permit 1/2/4/6 fills per side per day; this is a count cap, not a notional turnover cap. Fixed expiry is disabled, `holding_days=1`, and `planned_exit_date` is null.

## Install and run

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx plugin install plugins/qlib_strategy --target http://research.example:1024
axonx submit --task qlib_strategy_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 10 --replacement-fraction 0.2 --rank-buffer 1 \
  --transaction-cost-rate 0.001 --target http://research.example:1024
```

Reuse successful base or factor predictions. Record returned Task / Run IDs and wait for success before reading results. Upstream `qlib_strategy_etl`, `qlib_strategy_analysis`, `qlib_strategy_train` and `qlib_strategy_predict` register factor-layer implementations; policy comparisons reuse predictions. With the core from this checkout, Task-only wheel updates through the remote installation Job apply without restarting; restart when `restart_required` is true and verify Task definitions. Direct pip/source changes and older cores without plugin import refresh require restart. The core must support `portfolio_policy` and side fees.

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

Freeze upstream stock_risk prediction `predict#qlib_factor_predict#2026100917Z7Ys`; both policy schemes reuse it without retraining.

Both policy schemes use `replacement_fraction=0.2` and `rank_buffer=1`: after the minimum age, exit the worst-ranked holdings outside TopN first. Top20 allows 4 fills per side per day, Top30 allows 6; initial entry is exempt. In rank-retention mode, `holding_days=1` does not impose fixed expiry and planned_exit_date=null. The cap counts stocks, not turnover notional. Ten days is the predeclared main scheme; three days is exploratory. The policy default remains 10 days.

### Metric definitions

Overall IC/RankIC averages daily Pearson/Spearman correlations between predictions and valid next-day labels on signal-date eligible stocks, independently of holdings and TopN. Unannualized RankICIR = mean(daily RankIC)/std(daily RankIC,ddof=1); the annualized version multiplies by sqrt(252). Both are shown to distinguish backtest and factor-analysis conventions.

Net annualized = (∏(1+r_net))^(252/D)−1; net Sharpe = (mean(r_net)−[(1.012)^(1/252)−1])/std(r_net,ddof=1)×sqrt(252). Drawdown uses compounded net equity with initial equity 1 included in the running peak. Turnover = (executed buys+sells)/prior equity; full replacement is about 200%. Win rate is the share of positive net-return dates.

The universe-mean benchmark equally weights the full prediction cross-section with valid forward labels, not just Top20 and not the clipped mean used in risk features. HS300 is a constituent-weighted return proxy with at least 98% weight coverage, not the official CSI300 index quote series. Both benchmarks have 908 valid dates, 20230104–20261008. Net active metrics use this shared window; portfolio-only metrics use all 909 dates.

Net daily active return a_t = r_net,t−r_benchmark,t. **Net IR** = mean(a)/std(a,ddof=1)×sqrt(252). Net active annualized return compounds ∏(1+a) and annualizes over 908 dates; active drawdown uses the same compounded active-return curve. These are neither differences of annualized returns nor portfolio/benchmark equity ratios. Framework information_ratio fields use gross returns; this section recomputes net metrics from daily artifacts.

### Overall signals and full Top20 results

| Metric                                   | Strategy: 10d | Strategy: 3d |
| ---------------------------------------- | ------------: | -----------: |
| Overall IC                               |        0.0545 |       0.0545 |
| Overall RankIC                           |        0.0966 |       0.0966 |
| Overall RankICIR (annualized)            |       14.2859 |      14.2859 |
| Overall RankICIR (unannualized)          |        0.8999 |       0.8999 |
| Net annualized                           |        17.16% |       32.36% |
| Net cumulative return                    |        77.06% |      174.92% |
| Net Sharpe                               |        0.7026 |       1.1571 |
| Net annualized volatility                |        25.49% |       26.19% |
| Max drawdown                             |       -26.68% |      -24.91% |
| Daily return win rate                    |        51.93% |       55.89% |
| Mean daily two-sided turnover            |        19.23% |       40.02% |
| Mean daily cost / prior equity           |       0.0192% |      0.0400% |
| Closed trades                            |         1,739 |        3,624 |
| Net active annualized vs universe mean   |         4.79% |       18.65% |
| Net IR vs universe mean                  |        0.4387 |       1.4547 |
| Net active max drawdown vs universe mean |       -19.46% |      -18.63% |
| Net active annualized vs HS300 proxy     |        11.53% |       26.04% |
| Net IR vs HS300 proxy                    |        0.6713 |       1.2699 |
| Net active max drawdown vs HS300 proxy   |       -22.00% |      -23.96% |

### Top30 results

| Scheme        | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| ------------- | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Strategy: 10d |         18.60% |     0.7615 |      -28.32% |   19.45% |           0.5895 |        0.7631 |
| Strategy: 3d  |         29.29% |     1.0880 |      -25.53% |   40.03% |           1.4086 |        1.1912 |

### Top20 yearly results

| Year | Days | Strategy: 10d | Strategy: 3d |
| ---- | ---: | ------------: | -----------: |
| 2023 |  242 |         5.39% |        9.65% |
| 2024 |  242 |         4.25% |       17.73% |
| 2025 |  243 |        43.69% |       72.54% |
| 2026 |  182 |        19.94% |       39.43% |

Yearly values are interval net annualized returns; 2026 ends October 8. Results report `incomplete_market_data`: missing quotes may delay exits and carry stale marks. Same-close fills are a proxy.The 3-day scheme is exploratory on a reused development window, without independent confirmation; the default remains 10 days.

### Reproduce the experiment

Save Task/Run IDs and wait for success before each downstream submission; use the same `--target` for remote commands. Parameters below match the Setting table; verify remaining defaults with `get_task_definition` before submission.

```bash
axonx submit --task qlib_strategy_backtest --source-tasks '<stock_risk_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 10 \
  --replacement-fraction 0.2 --rank-buffer 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<market_path>' --calendar-file '<calendar_path>' --labels-file '<labels_path>'
```

For the exploratory 3-day scheme, change only `--minimum-holding-days` to 3; keep predictions and other inputs fixed.

### Task provenance and input checks

Execution workspace: `/nas/jinli.yl/data/axon` on machine 45.

| Stage / scheme          | Task ID                                          | Run ID                             |
| ----------------------- | ------------------------------------------------ | ---------------------------------- |
| Strategy: 10d: backtest | `backtest#qlib_strategy_backtest#202610091847QW` | `f08ccc6d681648c9b63e96cacaad51b4` |
| Strategy: 3d: backtest  | `backtest#qlib_strategy_backtest#2026100918JP6A` | `6e7306c9d9a54cdeb6c2aee6a36bd73d` |

| Input    | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

Core/plugin versions: 0.1.1 / 0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0. New data do not guarantee reproduction of the unpublished historical snapshot; raw artifacts are not committed.
