---
title: Experiment Design and Independent Confirmation
description: Fix controls, run ablations, lock a configuration, and evaluate evidence on an independent window.
---

# Experiment Design and Independent Confirmation

AxonX preserves execution evidence; experiment design determines which conclusions that evidence supports. This guide organizes a parameter or feature change into an inspectable comparison. Plugin documentation maintains specific algorithms and each plugin’s final experiment settings and results.

![Screening, configuration lock, and independent confirmation](../../figures/research/experiments.svg)

## Define the question and controls first

Before execution, record the hypothesis, baseline, candidates, selection rule, and evaluation windows. When comparing features, fix the data snapshot, labels, sample filters, training parameters, and backtest assumptions. When comparing costs or portfolio management, fix compatible prediction artifacts.

| Record                                | How to check it                                                                                         |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Execution service and plugin versions | Keep the target address, service version, plugin version or source revision                             |
| Data snapshot and timing              | Keep sources, coverage, partitions, and validation information; establish when signals become available |
| Samples and model                     | Keep labels, filters, training and validation windows, hyperparameters, and random seeds                |
| Execution and costs                   | Keep universe, fill proxy, delayed exits, cost rate, annualization, and risk-free settings              |
| Selection rule                        | Specify candidates, primary metrics, constraints, and tie handling beforehand                           |
| Experiment evidence                   | Keep Task/Run IDs, inputs, metadata, logs, and key artifacts                                            |

A fixed random seed does not replace fixed data and dependencies. Feature timing must respect information available at prediction time; future labels or future tradability must not determine features.

## Separate training, screening, and confirmation

1. **Training and validation**: select model parameters or early-stopping rounds within the training window.
2. **Screening**: compare candidates on a predefined out-of-sample window using the predefined rule.
3. **Locking**: record the choice, feature groups, model parameters, and execution protocol.
4. **Independent confirmation**: compare only the baseline and locked configuration; do not use this window to select more groups or tune parameters.

A selection window cannot also serve as independent confirmation. If confirmation results lead to further changes, treat that window as development information and establish a new confirmation design for the new configuration.

The current Qlib Factor experiment trains on `[20150101,20230101)` and selects groups using training-period validation RankIC, then reports a shared OOS interval from 2023. Qlib Strategy fixes the primary policy in advance and reports holding-period comparisons separately. Final three-layer comparisons appear below; each plugin records only its own settings and results.

## Preserve ablation chains with Tasks

Reuse compatible upstream data where possible, giving each candidate distinct Train, Predict, and Backtest identities. Keep the actual returned Task/Run IDs and wait for success before submitting downstream stages. The framework records lineage but does not run an entire DAG automatically.

```text
Shared ETL
  ├─ Baseline Train → Screening Predict → Screening Backtest
  └─ Candidate Train → Screening Predict → Screening Backtest
After locking
  ├─ Baseline Train → Confirmation Predict → Confirmation Backtest
  └─ Locked Train → Confirmation Predict → Confirmation Backtest
```

Use generated names or distinct explicit names; reusing a name replaces a terminal task directory. Preserve reasons for failures and invalidated runs instead of reporting only successes. See the [research workflow](workflow.md) for commands and waiting, and the factor plugin's [reproduction guide](../../../plugins/qlib_factor/README.md#install-and-run) for feature-group ablations.

## Compare common windows and matching definitions

Check protocols, data, dates, Top N, costs, and annualization before comparing returns and risk. Studio [strategy comparison](strategy-comparison.md) aligns common valid dates and recomputes metrics; date alignment does not establish matching research settings automatically.

Report signal quality and portfolio returns separately. RankIC measures ranking correlation. Net returns, drawdown, and Sharpe also depend on costs, fills, and exit assumptions. Improvement at one Top N does not imply improvement at every portfolio size.

[Backtest interpretation](backtest.md) distinguishes plugin summaries, frontend window calculations, gross returns, and net returns. Extra experiment calculations such as net Sharpe must declare formulas and data sources; the original artifact's gross Sharpe cannot substitute for net Sharpe.

## Interpret increments and uncertainty

Baseline and enhanced observations on the same dates can form paired differences. Report effective samples, missing dates, and treatment of temporal dependence alongside point estimates. Record the statistic, block length, resampling count, and random seed for block bootstrap calculations.

Circular block bootstrap can estimate uncertainty in paired daily RankIC or net-return differences. Record block length, resample count and seed, and distinguish daily mean differences from compounded annualized return differences. The current three-layer comparison reports point estimates, all candidates and data-quality checks.

This is experiment analysis; Studio's strategy comparison page does not automatically generate that bootstrap test. Retain original daily artifacts, alignment methods, and calculation records in the experiment environment.

## Inspect the agent-developed enhancement case

The [project benchmark](../../../README.md#benchmark-agent-developed-market-cross-sectional-features) explains how an agent developed a separate plugin and executed research through AxonX. [Qlib Factor](../../../plugins/qlib_factor/README.md) maintains feature definitions, Task parameters, conclusions, and reproduction commands.

Shared cross-plugin settings, full metrics and controls appear in the [three-layer comparison](#comparison). Each plugin README maintains its own detailed settings and results. Original logs, metadata and daily artifacts remain in the execution workspace.

## Report the conclusion

Report the baseline and locked configuration, selection process, independent window, metric changes, and uncertainty. Include failures, declining metrics, and limitations of trading assumptions. Task success establishes completed execution; the research conclusion still needs this evidence.

<a id="comparison"></a>

## Three-layer experiment settings and result comparison

This section consolidates shared experiment settings, final schemes and necessary controls across the three plugins. Each plugin documents only its own detailed settings and results. Shared settings appear once; the scheme table lists differences. Experiment CSV/JSON, intermediate candidates, historical reports and archives have been removed. Results come from successful machine-45 Tasks and their original metadata, summary.parquet, daily.parquet and trades.parquet, after checking dates and input hashes. No models or backtests were rerun; original artifacts remain in the execution workspace.

### Shared Setting

| Stage                 | Setting                                                                                                                                                                                                                                                                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data / universe       | Tushare adjusted prices and volumes; Shanghai/Shenzhen excluding Beijing, with no CSI300-only selection. ETL output 20150101–20261008: 11,446,950 rows and 5,477 stocks; 158 base columns, 171 columns in factor ETL. min_history_coverage=0.8; no forward-filling suspensions or missing quotes.                                                               |
| Training dates        | `[20150101,20230101)`; both signal date and label_target_date precede the exclusive cutoff. Internal validation starts 20220316, using the last 10% of dates.                                                                                                                                                                                                   |
| Labels / filtering    | Adjusted signal-close to next-market-close returns; retain signal-date buyable rows with valid fixed-one-day labels available before cutoff. Trim 2.5% of raw returns at each daily tail; normalize average ranks to [0,1], singleton=0.5; transform fitting and validation samples separately. label_winsorize_tail=0.025; this experiment uses rank, not CSZ. |
| Sample counts         | 6,147,420 rows before trimming; full-period refit on 5,838,557 rows after trimming; tuning train 5,010,901 and validation 823,601 rows.                                                                                                                                                                                                                         |
| LightGBM              | 4.7.0, parameter_preset=axonx, objective=regression, metric=[l2,l1]; learning_rate=0.03, num_leaves=31, max_depth=-1, min_data_in_leaf=20, bagging_fraction=0.9, bagging_freq=1, lambda_l1=lambda_l2=0. See scheme-specific feature_fraction below.                                                                                                             |
| Rounds / refit        | num_boost_round=1000, early_stopping_rounds=50; validation L2 selects rounds before refitting all training samples. Training-validation RankIC selects the final factor candidate.                                                                                                                                                                              |
| Determinism           | random_seed=42; LightGBM seed, feature_fraction_seed, bagging_seed and data_random_seed all 42; num_threads=8, deterministic=true, force_col_wise=true.                                                                                                                                                                                                         |
| Out of sample         | pred_start=20230101, pred_end=20261008; actual overall evaluation 20230103–20261008, 909 market dates. 2026 is incomplete.                                                                                                                                                                                                                                      |
| Portfolio / execution | Top20 primary, Top30 secondary; same-close quote proxy, sells before buys, price-limit and eligibility constraints. New entries receive at most 1/N equity; no replacement for unfilled entries, blocked exits retain capital, retained weights are not rebalanced. No forced final liquidation.                                                                |
| Fees / annualization  | transaction_cost_rate=0.001 on each executed side; buy_cost_rate=sell_cost_rate=null uses the shared rate, without a minimum fee. annualization_days=252, annual_risk_free_rate=0.012.                                                                                                                                                                          |
| Shared inputs         | All six backtests use the base ETL market.parquet, calendar.parquet and labels.parquet; as_of_date=20261008, index_codes=[], minimum_index_weight_coverage=0.98.                                                                                                                                                                                                |

### Final scheme differences

| Scheme                | context_groups | Features | feature_fraction | Best rounds | Validation RankIC | Exit policy             |
| --------------------- | -------------- | -------: | ---------------: | ----------: | ----------------: | ----------------------- |
| Alpha158              | —              |      158 |              0.9 |         422 |           0.10789 | fixed holding_days=1    |
| Factor: stock_risk    | risk           |      160 |              1.0 |         426 |           0.11321 | fixed holding_days=1    |
| Strategy: 10d         | risk           |      160 |              1.0 |         426 |           0.11321 | minimum_holding_days=10 |
| Strategy: 3d          | risk           |      160 |              1.0 |         426 |           0.11321 | minimum_holding_days=3  |
| Alpha158 + 10d        | —              |      158 |              0.9 |         422 |           0.10789 | minimum_holding_days=10 |
| Matched Alpha158 + 3d | none           |      158 |              1.0 |         397 |           0.10776 | minimum_holding_days=3  |

All four policy backtests use `replacement_fraction=0.2` and `rank_buffer=1`: after the minimum age, exit the worst-ranked holdings outside TopN first. Top20 allows 4 fills per side per day, Top30 allows 6; initial entry is exempt. In rank-retention mode, `holding_days=1` does not impose fixed expiry and planned_exit_date=null. The cap counts stocks, not turnover notional. Ten days is the predeclared main scheme; three days is exploratory. Defaults remain 10 days for policy and none for context groups.

stock_risk adds only `f_context_residual_vol20` and `f_context_downside_risk20`, without global moments or neutral columns. Its saved `context_windows=[10]` filters only global moments and therefore has no effect on risk features. Stock daily returns are clipped at contemporaneous cross-sectional 2%/98% linear quantiles; market return is the clipped equal-weight mean. Beta uses 60 market dates through T−1 with at least 30 valid paired returns, covariance/market variance, clipped to [−3,3]; market variance ≤1e−12 leaves beta undefined. Daily residual return is clipped stock return minus historical beta × market return. Residual volatility is its 20-day sample standard deviation (ddof=1); downside risk is sqrt(mean(min(clipped daily return,0)²)). Both require at least 16 valid observations in 20 dates; missing/undefined values remain missing.

### Metric definitions

Overall IC/RankIC averages daily Pearson/Spearman correlations between predictions and valid next-day labels on signal-date eligible stocks, independently of holdings and TopN. Unannualized RankICIR = mean(daily RankIC)/std(daily RankIC,ddof=1); the annualized version multiplies by sqrt(252). Both are shown to distinguish backtest and factor-analysis conventions.

Net annualized = (∏(1+r_net))^(252/D)−1; net Sharpe = (mean(r_net)−[(1.012)^(1/252)−1])/std(r_net,ddof=1)×sqrt(252). Drawdown uses compounded net equity with initial equity 1 included in the running peak. Turnover = (executed buys+sells)/prior equity; full replacement is about 200%. Win rate is the share of positive net-return dates.

The universe-mean benchmark equally weights the full prediction cross-section with valid forward labels, not just Top20 and not the clipped mean used in risk features. HS300 is a constituent-weighted return proxy with at least 98% weight coverage, not the official CSI300 index quote series. Both benchmarks have 908 valid dates, 20230104–20261008. Net active metrics use this shared window; portfolio-only metrics use all 909 dates.

Net daily active return a_t = r_net,t−r_benchmark,t. **Net IR** = mean(a)/std(a,ddof=1)×sqrt(252). Net active annualized return compounds ∏(1+a) and annualizes over 908 dates; active drawdown uses the same compounded active-return curve. These are neither differences of annualized returns nor portfolio/benchmark equity ratios. Framework information_ratio fields use gross returns; this section recomputes net metrics from daily artifacts.

### Overall signals and full Top20 metrics

| Metric                                   | Alpha158 | Factor: stock_risk | Strategy: 10d | Strategy: 3d |
| ---------------------------------------- | -------: | -----------------: | ------------: | -----------: |
| Overall IC                               |   0.0530 |             0.0545 |        0.0545 |       0.0545 |
| Overall RankIC                           |   0.0923 |             0.0966 |        0.0966 |       0.0966 |
| Overall RankICIR (annualized)            |  12.8817 |            14.2859 |       14.2859 |      14.2859 |
| Overall RankICIR (unannualized)          |   0.8115 |             0.8999 |        0.8999 |       0.8999 |
| Net annualized                           |    7.69% |              9.04% |        17.16% |       32.36% |
| Net cumulative return                    |   30.63% |             36.64% |        77.06% |      174.92% |
| Net Sharpe                               |   0.3624 |             0.4054 |        0.7026 |       1.1571 |
| Net annualized volatility                |   28.20% |             28.53% |        25.49% |       26.19% |
| Max drawdown                             |  -38.64% |            -40.67% |       -26.68% |      -24.91% |
| Daily return win rate                    |   53.47% |             53.47% |        51.93% |       55.89% |
| Mean daily two-sided turnover            |  198.83% |            199.35% |        19.23% |       40.02% |
| Mean daily cost / prior equity           |  0.1988% |            0.1993% |       0.0192% |      0.0400% |
| Closed trades                            |   18,032 |             18,079 |         1,739 |        3,624 |
| Net active annualized vs universe mean   |   -3.47% |             -1.86% |         4.79% |       18.65% |
| Net IR vs universe mean                  |  -0.1404 |            -0.0649 |        0.4387 |       1.4547 |
| Net active max drawdown vs universe mean |  -28.47% |            -21.71% |       -19.46% |      -18.63% |
| Net active annualized vs HS300 proxy     |    2.77% |              4.09% |        11.53% |       26.04% |
| Net IR vs HS300 proxy                    |   0.2353 |             0.2947 |        0.6713 |       1.2699 |
| Net active max drawdown vs HS300 proxy   |  -31.94% |            -29.34% |       -22.00% |      -23.96% |

### Same-policy controls: Top20

| Metric                                   | Alpha158 + 10d | Matched Alpha158 + 3d |
| ---------------------------------------- | -------------: | --------------------: |
| Overall IC                               |         0.0530 |                0.0529 |
| Overall RankIC                           |         0.0923 |                0.0922 |
| Overall RankICIR (annualized)            |        12.8817 |               12.9202 |
| Overall RankICIR (unannualized)          |         0.8115 |                0.8139 |
| Net annualized                           |         18.69% |                22.62% |
| Net cumulative return                    |         85.55% |               108.64% |
| Net Sharpe                               |         0.7414 |                0.9010 |
| Net annualized volatility                |         26.13% |                24.72% |
| Max drawdown                             |        -32.24% |               -36.19% |
| Daily return win rate                    |         54.90% |                56.11% |
| Mean daily two-sided turnover            |         19.77% |                40.01% |
| Mean daily cost / prior equity           |        0.0198% |               0.0400% |
| Closed trades                            |          1,799 |                 3,624 |
| Net active annualized vs universe mean   |          5.93% |                 9.01% |
| Net IR vs universe mean                  |         0.4543 |                0.6364 |
| Net active max drawdown vs universe mean |        -29.07% |               -25.97% |
| Net active annualized vs HS300 proxy     |         13.00% |                16.56% |
| Net IR vs HS300 proxy                    |         0.7197 |                0.9150 |
| Net active max drawdown vs HS300 proxy   |        -26.76% |               -30.31% |

The base model earns 18.69% with the 10-day policy, above the augmented model’s 17.16%. The augmented 3-day scheme earns 32.36%, above the matched control’s 22.62%, with better net Sharpe and drawdown. Three days increases turnover versus ten days; exploratory selection is not independent confirmation and does not change defaults.

### Benchmark performance (908 dates)

| Benchmark     | Annualized | Cumulative | Annualized volatility | Max drawdown | Daily win rate |
| ------------- | ---------: | ---------: | --------------------: | -----------: | -------------: |
| Universe mean |     11.12% |     46.22% |                25.06% |      -33.66% |         54.74% |
| HS300 proxy   |      5.03% |     19.33% |                17.58% |      -22.46% |         49.78% |

### Secondary Top30 comparison

| Scheme                | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| --------------------- | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Alpha158              |          0.99% |     0.1315 |      -40.59% |  199.03% |          -0.5933 |       -0.0776 |
| Factor: stock_risk    |          4.27% |     0.2480 |      -41.41% |  199.37% |          -0.4236 |        0.0840 |
| Strategy: 10d         |         18.60% |     0.7615 |      -28.32% |   19.45% |           0.5895 |        0.7631 |
| Strategy: 3d          |         29.29% |     1.0880 |      -25.53% |   40.03% |           1.4086 |        1.1912 |
| Alpha158 + 10d        |         22.57% |     0.8876 |      -31.95% |   19.78% |           0.7104 |        0.9347 |
| Matched Alpha158 + 3d |         20.43% |     0.8395 |      -33.71% |   40.02% |           0.5513 |        0.8412 |

### Top20 yearly stability

| Year | Days | Alpha158 | Factor: stock_risk | Strategy: 10d | Strategy: 3d |
| ---- | ---: | -------: | -----------------: | ------------: | -----------: |
| 2023 |  242 |   -9.16% |            -10.08% |         5.39% |        9.65% |
| 2024 |  242 |    5.09% |             10.54% |         4.25% |       17.73% |
| 2025 |  243 |   48.64% |             56.68% |        43.69% |       72.54% |
| 2026 |  182 |   -9.30% |            -14.73% |        19.94% |       39.43% |

Values are net annualized returns for each yearly interval; 2026 ends October 8. All schemes report `incomplete_market_data`: missing quotes can delay exits and carry stale marks, so evaluation is provisional. Same-close fills remain a proxy. Top20 delayed-expiry events total 84 for base and 60 for factor; policies have no planned expiry and report 0 for that field, which does not imply no blocked sell orders. All six schemes end with 20 unsettled positions.

### Reproduce the final Setting

Prepare data and install all three plugins using the [research workflow](workflow.md). Save each Task/Run ID and wait for success before downstream submission; add the same `--target` to remote commands. Training commands explicitly specify experiment-changing parameters; other shared settings use the defaults listed above, verified with `get_task_definition` before submission. Controls use identical base market, calendar and label files.

```bash
# Base model: 158 features
axonx submit --task qlib_a158_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_a158_train --source-tasks '<base_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 0.9 --random-seed 42 --num-threads 8
axonx submit --task qlib_a158_predict --source-tasks '<base_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# Final factor model: 158 base + 2 risk features
axonx submit --task qlib_factor_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_factor_train --source-tasks '<factor_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --context-groups risk --context-windows '[10]' \
  --feature-fraction 1.0 --random-seed 42 --num-threads 8
axonx submit --task qlib_factor_predict --source-tasks '<factor_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# Fixed holding: run once for base and once for factor predictions
axonx submit --task qlib_factor_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'

# Predeclared 10-day policy; change minimum-holding-days to 3 for exploration
axonx submit --task qlib_strategy_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 10 \
  --replacement-fraction 0.2 --rank-buffer 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'
```

For the base fixed-expiry scheme, use `qlib_a158_backtest` and base predictions. For the base 10-day policy, change only the prediction source. For the matched 3-day control, retrain on the same factor ETL with context_groups=none and feature_fraction=1, keep other settings fixed, predict and apply the 3-day policy. New data do not guarantee reproduction of the unpublished historical snapshot; avoid overwriting results by reusing explicit task names.

### Final Task provenance and input checks

Execution workspace: `/nas/jinli.yl/data/axon` on machine 45. Only final chains are retained below.

| Stage / scheme                  | Task ID                                          | Run ID                             |
| ------------------------------- | ------------------------------------------------ | ---------------------------------- |
| baseline: train                 | `train#qlib_a158_train#2026100912mMlp`           | `710de1c0530b430e94e0b92e7634cd2a` |
| baseline: predict               | `predict#qlib_a158_predict#2026100912Qanw`       | `c8b97e5ec7bb483da455d988ec6216d3` |
| full_none: train                | `train#qlib_factor_train#2026100916Lsy1`         | `a57d863cc3274580a3771faa31412f44` |
| full_none: predict              | `predict#qlib_factor_predict#2026100917IgPv`     | `3ad34a2542584fd8b6b6e70296ac4e6b` |
| stock_risk: train               | `train#qlib_factor_train#2026100917VGxi`         | `d55e035ab9c549ab840770b1e8444f10` |
| stock_risk: predict             | `predict#qlib_factor_predict#2026100917Z7Ys`     | `1a033666806b4e359c6acc11f8b02399` |
| Alpha158: backtest              | `backtest#qlib_a158_backtest#2026100916Y0Xb`     | `d10c8a78be104ee7a8a492b9cc438bde` |
| Factor: stock_risk: backtest    | `backtest#qlib_factor_backtest#2026100917v6ku`   | `37cf5867c5d344da9c4b6a9b56bc6e24` |
| Strategy: 10d: backtest         | `backtest#qlib_strategy_backtest#202610091847QW` | `f08ccc6d681648c9b63e96cacaad51b4` |
| Strategy: 3d: backtest          | `backtest#qlib_strategy_backtest#2026100918JP6A` | `6e7306c9d9a54cdeb6c2aee6a36bd73d` |
| Alpha158 + 10d: backtest        | `backtest#qlib_strategy_backtest#2026100918E4QT` | `3a28ad8734d949eb9b6289790dfe366b` |
| Matched Alpha158 + 3d: backtest | `backtest#qlib_strategy_backtest#20261009185kDS` | `f98fe8ba2d7045d1a7588e04a82301ca` |

| Input                             | SHA-256                                                            |
| --------------------------------- | ------------------------------------------------------------------ |
| market                            | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar                          | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels                            | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| Alpha158: prediction              | `3337bb98e59986b3d3e10730ecff49fae0d3d31b7d6b8e163fe19a63510a8aad` |
| Factor: stock_risk: prediction    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |
| Matched Alpha158 + 3d: prediction | `694553443c32336eb274e6998c884dd59444f0a5561381162c1fe236863b7101` |

Base ETL: `etl#qlib_a158_etl#2026100912u43E`; final factor ETL: `etl#qlib_factor_etl#2026100917HM2p`. Policies sharing a model have identical prediction hashes; all six share market/calendar/label hashes. Core/plugin versions are 0.1.1 / 0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0. The historical execution environment received the portfolio_policy extension; deploy a current source version supporting it.

[Alpha158](../../../plugins/qlib_a158/README.md#experiments) · [Qlib Factor](../../../plugins/qlib_factor/README.md#experiments) · [Qlib Strategy](../../../plugins/qlib_strategy/README.md#experiments)
