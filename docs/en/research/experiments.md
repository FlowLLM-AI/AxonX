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

The current Qlib Factor experiment trains on `[20150101,20230101)` and selects groups using training-period validation RankIC, then reports a shared OOS interval from 2023. Qlib Strategy presents the better-performing 3-day candidate, which has not been independently confirmed. The three-version comparison appears below.

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

Circular block bootstrap can estimate uncertainty in paired daily RankIC or net-return differences. Record block length, resample count and seed, and distinguish daily mean differences from compounded annualized return differences. The current three-version comparison reports point estimates, selection evidence, and data-quality limits.

This is experiment analysis; Studio's strategy comparison page does not automatically generate that bootstrap test. Retain original daily artifacts, alignment methods, and calculation records in the experiment environment.

## Inspect the agent-developed enhancement case

The [project benchmark](../../../README.md#benchmark-agent-developed-market-cross-sectional-features) explains how an agent developed a separate plugin and executed research through AxonX. [Qlib Factor](../../../plugins/qlib_factor/README.md) describes feature definitions, Task parameters and execution commands.

Shared settings, full metrics, and selection evidence for the three versions appear in the [experiment comparison](#comparison). Plugin READMEs describe algorithms and configuration. Original logs, metadata, and daily artifacts remain in the execution workspace.

## Report the conclusion

Report the baseline and locked configuration, selection process, independent window, metric changes, and uncertainty. Include failures, declining metrics, and limitations of trading assumptions. Task success establishes completed execution; the research conclusion still needs this evidence.

<a id="comparison"></a>

## Three plugins, three experiment versions

The documentation presents three successive versions: the Alpha158 baseline, two added risk factors, and a 3-day rank-retention policy reusing augmented predictions. They correspond to `qlib_a158`, `qlib_factor`, and `qlib_strategy`. This page maintains shared settings and metric definitions; plugin READMEs describe algorithms and configuration. Values come from successful machine-45 Tasks and metadata, summary.parquet, daily.parquet, and trades.parquet, with dates and input hashes checked. No training or backtests were rerun; original artifacts remain in the execution workspace.

These tables record historical private-workspace runs, not a rerun of the current checkout. Current stock features require a valid quote on the signal date; reproduction commands below use the current explicit buy/sell fee fields. Exact metric reproduction requires the original data snapshot and a new full run.

The recorded experiments used symmetric 0.1% buy/sell fees; the table and reproduction commands retain those settings. Current defaults match Qlib: 0.05% buy and 0.15% sell. Historical metrics do not represent results under these defaults.

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
| Fees / annualization  | buy_cost_rate=sell_cost_rate=0.001 on executed notional, without a minimum fee. annualization_days=252, annual_risk_free_rate=0.012.                                                                                                                                                                                                                            |
| Shared inputs         | All three versions use the base ETL market.parquet, calendar.parquet and labels.parquet; as_of_date=20261008, index_codes=[], minimum_index_weight_coverage=0.98.                                                                                                                                                                                               |

### Final scheme differences

| Scheme             | Plugin          | context_groups | Features | feature_fraction | Best rounds | Validation RankIC | Exit policy            |
| ------------------ | --------------- | -------------- | -------: | ---------------: | ----------: | ----------------: | ---------------------- |
| Alpha158           | `qlib_a158`     | —              |      158 |              0.9 |         422 |           0.10789 | fixed holding_days=1   |
| Factor: stock_risk | `qlib_factor`   | risk           |      160 |              1.0 |         426 |           0.11321 | fixed holding_days=1   |
| Strategy: 3d       | `qlib_strategy` | risk           |      160 |              1.0 |         426 |           0.11321 | minimum_holding_days=3 |

The strategy version explicitly uses `minimum_holding_days=3`, `replacement_fraction=0.2`, and `rank_buffer=1`: after the minimum age, exit the worst-ranked holdings outside TopN first. Top20 allows 4 fills per side daily and Top30 allows 6; initial entry is exempt. The strategy has no fixed-expiry parameter; planned_exit_date=null. This is a stock-count cap. Plugin defaults remain 10 days and context_groups=none; both augmented versions require explicit parameters.

The factor version adds only residual volatility and downside risk to the 158 base columns (`context_groups=risk`). Timing, missing-value requirements, and formulas are maintained in [Qlib Factor](../../../plugins/qlib_factor/README.md). The strategy version reuses those predictions without retraining, so overall signal metrics are identical.

### Metric definitions

Overall IC/RankIC averages daily Pearson/Spearman correlations between predictions and valid next-day labels on signal-date eligible stocks, independently of holdings and TopN. Tables report only annualized RankICIR = mean(daily RankIC)/std(daily RankIC,ddof=1) × sqrt(252). Convert unannualized factor-analysis values before comparing them.

Net annualized = (∏(1+r_net))^(252/D)−1; net Sharpe = (mean(r_net)−[(1.012)^(1/252)−1])/std(r_net,ddof=1)×sqrt(252). Drawdown uses compounded net equity with initial equity 1 included in the running peak. Turnover = (executed buys+sells)/prior equity; full replacement is about 200%. Win rate is the share of positive net-return dates.

The universe-mean benchmark equally weights the full prediction cross-section with valid forward labels, not just Top20 and not the clipped mean used in risk features. HS300 is a constituent-weighted return proxy with at least 98% weight coverage, not the official CSI300 index quote series. Both benchmarks have 908 valid dates, 20230104–20261008. Net active metrics use this shared window; portfolio-only metrics use all 909 dates.

Net daily active return a_t = r_net,t−r_benchmark,t. **Net IR** = mean(a)/std(a,ddof=1)×sqrt(252). Net active annualized return compounds ∏(1+a) and annualizes over 908 dates; active drawdown uses the same compounded active-return curve. These are neither differences of annualized returns nor portfolio/benchmark equity ratios. Framework information_ratio fields use gross returns; this section recomputes net metrics from daily artifacts.

![Signal quality for baseline and risk factors](../../figures/benchmark/qlib-signal-quality.svg)

![Net annualized returns for the three research versions](../../figures/benchmark/qlib-topn-results.svg)

### Overall signals and full Top20 metrics

| Metric                                   | Alpha158 | Factor: stock_risk | Strategy: 3d |
| ---------------------------------------- | -------: | -----------------: | -----------: |
| Overall IC                               |   0.0530 |             0.0545 |       0.0545 |
| Overall RankIC                           |   0.0923 |             0.0966 |       0.0966 |
| Overall RankICIR (annualized)            |  12.8817 |            14.2859 |      14.2859 |
| Net annualized                           |    7.69% |              9.04% |       32.36% |
| Net cumulative return                    |   30.63% |             36.64% |      174.92% |
| Net Sharpe                               |   0.3624 |             0.4054 |       1.1571 |
| Net annualized volatility                |   28.20% |             28.53% |       26.19% |
| Max drawdown                             |  -38.64% |            -40.67% |      -24.91% |
| Daily return win rate                    |   53.47% |             53.47% |       55.89% |
| Mean daily two-sided turnover            |  198.83% |            199.35% |       40.02% |
| Mean daily cost / prior equity           |  0.1988% |            0.1993% |      0.0400% |
| Closed trades                            |   18,032 |             18,079 |        3,624 |
| Net active annualized vs universe mean   |   -3.47% |             -1.86% |       18.65% |
| Net IR vs universe mean                  |  -0.1404 |            -0.0649 |       1.4547 |
| Net active max drawdown vs universe mean |  -28.47% |            -21.71% |      -18.63% |
| Net active annualized vs HS300 proxy     |    2.77% |              4.09% |       26.04% |
| Net IR vs HS300 proxy                    |   0.2353 |             0.2947 |       1.2699 |
| Net active max drawdown vs HS300 proxy   |  -31.94% |            -29.34% |      -23.96% |

### Selection evidence and limits

The augmented 3-day policy has better net annualized return, net Sharpe, and drawdown than the 10-day candidate at both Top20 and Top30, so it is the sole strategy version shown. Its Top20 daily two-sided turnover is higher (40.02%). A same-parameter base-model control with the 3-day policy earns 22.62% at Top20, versus 32.36% for the augmented policy. This is exploratory selection on a reused development window, without independent confirmation. Base and factor feature_fraction differ (0.9 versus 1.0); return differences across the three versions cannot be attributed entirely to added factors.

### Benchmark performance (908 dates)

| Benchmark     | Annualized | Cumulative | Annualized volatility | Max drawdown | Daily win rate |
| ------------- | ---------: | ---------: | --------------------: | -----------: | -------------: |
| Universe mean |     11.12% |     46.22% |                25.06% |      -33.66% |         54.74% |
| HS300 proxy   |      5.03% |     19.33% |                17.58% |      -22.46% |         49.78% |

### Secondary Top30 comparison

| Scheme             | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| ------------------ | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Alpha158           |          0.99% |     0.1315 |      -40.59% |  199.03% |          -0.5933 |       -0.0776 |
| Factor: stock_risk |          4.27% |     0.2480 |      -41.41% |  199.37% |          -0.4236 |        0.0840 |
| Strategy: 3d       |         29.29% |     1.0880 |      -25.53% |   40.03% |           1.4086 |        1.1912 |

### Top20 yearly stability

| Year | Days | Alpha158 | Factor: stock_risk | Strategy: 3d |
| ---- | ---: | -------: | -----------------: | -----------: |
| 2023 |  242 |   -9.16% |            -10.08% |        9.65% |
| 2024 |  242 |    5.09% |             10.54% |       17.73% |
| 2025 |  243 |   48.64% |             56.68% |       72.54% |
| 2026 |  182 |   -9.30% |            -14.73% |       39.43% |

Values are net annualized returns for each yearly interval; 2026 ends October 8. All schemes report `incomplete_market_data`: missing quotes can delay exits and carry stale marks, so evaluation is provisional. Same-close fills remain a proxy. Top20 delayed-expiry events total 84 for base and 60 for factor; policies have no planned expiry and report 0 for that field, which does not imply no blocked sell orders. All three versions end with 20 unsettled positions.

### Reproduce the final Setting

Prepare data and install all three plugins using the [research workflow](workflow.md). Save each Task/Run ID and wait for success before downstream submission; add the same `--target` to remote commands. Training commands explicitly specify experiment-changing parameters; verify the remaining shared settings above with `get_task_definition` before submission. The three versions use identical base market, calendar, and label files.

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
  --top-ns '[20,30]' --holding-days 1 --buy-cost-rate 0.001 --sell-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'

# Strategy version: reuse factor predictions with the selected 3-day policy
axonx submit --task qlib_strategy_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 3 \
  --replacement-fraction 0.2 --rank-buffer 1 --buy-cost-rate 0.001 --sell-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'
```

For the baseline version, use `qlib_a158_backtest` with base predictions. New data do not guarantee reproduction of the unpublished historical snapshot; use distinct task names to preserve existing results.

### Final Task provenance and input checks

Execution workspace: `/nas/jinli.yl/data/axon` on machine 45. Only final chains are retained below.

| Stage / scheme               | Task ID                                          | Run ID                             |
| ---------------------------- | ------------------------------------------------ | ---------------------------------- |
| baseline: train              | `train#qlib_a158_train#2026100912mMlp`           | `710de1c0530b430e94e0b92e7634cd2a` |
| baseline: predict            | `predict#qlib_a158_predict#2026100912Qanw`       | `c8b97e5ec7bb483da455d988ec6216d3` |
| stock_risk: train            | `train#qlib_factor_train#2026100917VGxi`         | `d55e035ab9c549ab840770b1e8444f10` |
| stock_risk: predict          | `predict#qlib_factor_predict#2026100917Z7Ys`     | `1a033666806b4e359c6acc11f8b02399` |
| Alpha158: backtest           | `backtest#qlib_a158_backtest#2026100916Y0Xb`     | `d10c8a78be104ee7a8a492b9cc438bde` |
| Factor: stock_risk: backtest | `backtest#qlib_factor_backtest#2026100917v6ku`   | `37cf5867c5d344da9c4b6a9b56bc6e24` |
| Strategy: 3d: backtest       | `backtest#qlib_strategy_backtest#2026100918JP6A` | `6e7306c9d9a54cdeb6c2aee6a36bd73d` |

| Input                          | SHA-256                                                            |
| ------------------------------ | ------------------------------------------------------------------ |
| market                         | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar                       | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels                         | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| Alpha158: prediction           | `3337bb98e59986b3d3e10730ecff49fae0d3d31b7d6b8e163fe19a63510a8aad` |
| Factor: stock_risk: prediction | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

Base ETL: `etl#qlib_a158_etl#2026100912u43E`; final factor ETL: `etl#qlib_factor_etl#2026100917HM2p`. Policies sharing a model have identical prediction hashes; all three share market/calendar/label hashes. Core/plugin versions are 0.1.1 / 0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0.

[Alpha158](../../../plugins/qlib_a158/README.md) · [Qlib Factor](../../../plugins/qlib_factor/README.md) · [Qlib Strategy](../../../plugins/qlib_strategy/README.md)
