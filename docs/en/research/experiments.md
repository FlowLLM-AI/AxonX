---
title: Experiment Design and Independent Confirmation
description: Fix controls, run ablations, lock a configuration, and evaluate evidence on an independent window.
---

# Experiment Design and Independent Confirmation

AxonX preserves execution evidence; experiment design determines which conclusions that evidence supports. This guide organizes a parameter or feature change into an inspectable comparison. Plugin READMEs describe algorithms; this page maintains the experiment configuration and results.

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

The documented experiments fix the risk group and a 3-day strategy, train on `[20150101,20230101)`, and evaluate from 2023 without independent confirmation. The three-version comparison appears below.

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

## Three experiments

This page retains one experiment group run on machine 45 on 2026-10-10 from commit `8fc1174`: Alpha158, risk factors, and 3-day rank retention. Both models rerun ETL, training, prediction and backtesting from the same data snapshot; the strategy reuses the new factor-model predictions. Buy/sell fees are 0.05% / 0.15%; all other parameters retain the existing settings. Plugin READMEs describe algorithms and interfaces.

### Shared settings

| Setting                 | Value                                                                                                                                                                                     |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data / universe         | Tushare; Shanghai/Shenzhen excluding Beijing; 11,446,950 rows, 5,477 stocks; 158 / 171 ETL features; min_history_coverage=0.8.                                                            |
| Training / labels       | [20150101,20230101); label_return_rank; trim_tail=0.025; label_winsorize_tail=0.025; validation_ratio=0.10; cutoff-crossing labels excluded.                                              |
| Samples / validation    | refit=5,838,557; tuning=5,010,901; validation=823,601; validation_start=20220316                                                                                                          |
| Model                   | parameter_preset=axonx; learning_rate=0.03; num_leaves=31; max_depth=-1; min_data_in_leaf=20; bagging_fraction=0.9; bagging_freq=1; lambda_l1=lambda_l2=0; random_seed=42; num_threads=8. |
| Training rounds         | num_boost_round=1000; early_stopping_rounds=50; select by validation L2, then refit all training rows.                                                                                    |
| Prediction / evaluation | pred_start=20230101; pred_end=20261008; as_of_date=20261008; 909 market dates; top_ns=[20,30]; index_codes=[]; minimum_index_weight_coverage=0.98.                                        |
| Fees / annualization    | buy_cost_rate=0.0005; sell_cost_rate=0.0015; no minimum monetary fee; annualization_days=252; annual_risk_free_rate=0.012.                                                                |
| Execution               | Same-close quote proxy; sells before buys; no substitution for unfilled targets; no final forced liquidation; shared base ETL market/calendar/labels.                                     |

### Scheme settings

| Scheme         | Features | context_groups | feature_fraction | Best rounds | Validation RankIC |                   Exit |
| -------------- | -------: | -------------: | ---------------: | ----------: | ----------------: | ---------------------: |
| Alpha158       |      158 |              — |              0.9 |         422 |           0.10789 |         holding_days=1 |
| Risk factors   |      160 |           risk |              1.0 |         426 |           0.11321 |         holding_days=1 |
| 3-day strategy |      160 |           risk |              1.0 |         426 |           0.11321 | minimum_holding_days=3 |

The strategy uses `replacement_fraction=0.2` and `rank_buffer=1`: at most 4/6 filled orders per side daily for Top20/Top30, with initial construction exempt. The factor model selects only the two risk features; `context_windows=[10]` does not change their fixed horizons.

### Metric definitions

IC/RankIC average daily Pearson/Spearman correlations of eligible signal-date predictions and valid next-day labels. RankICIR is mean daily RankIC / sample standard deviation × sqrt(252). Net returns compound and annualize over 252 trading days; net Sharpe subtracts the daily risk-free return. Drawdown includes initial equity 1 in the running peak. Turnover and costs normalize by prior equity.

Universe mean equally weights valid forward-label returns; HS300 is a constituent-weighted proxy requiring 98% weight coverage. Net active return subtracts the daily benchmark from portfolio net return; net IR is its mean / sample standard deviation × sqrt(252). Active annualization and drawdown use compounded active returns on shared benchmark-valid dates.

![Signal quality](../../figures/benchmark/qlib-signal-quality.svg)

![Net annualized returns](../../figures/benchmark/qlib-topn-results.svg)

### Overall signals and Top20

| Metric                                   | Alpha158 | Risk factors | 3-day strategy |
| ---------------------------------------- | -------: | -----------: | -------------: |
| Overall IC                               |   0.0530 |       0.0545 |         0.0545 |
| Overall RankIC                           |   0.0923 |       0.0966 |         0.0966 |
| Overall RankICIR (annualized)            |  12.8817 |      14.2859 |        14.2859 |
| Net annualized                           |    7.67% |        9.03% |         32.37% |
| Net cumulative return                    |   30.56% |       36.60% |        174.99% |
| Net Sharpe                               |   0.3619 |       0.4052 |         1.1575 |
| Net annualized volatility                |   28.20% |       28.53% |         26.19% |
| Max drawdown                             |  -38.65% |      -40.69% |        -24.91% |
| Daily return win rate                    |   53.47% |       53.47% |         55.89% |
| Mean daily two-sided turnover            |  198.83% |      199.35% |         40.01% |
| Mean daily cost / prior equity           |  0.1989% |      0.1994% |        0.0400% |
| Closed trades                            |   18,032 |       18,079 |          3,624 |
| Net active annualized vs universe mean   |   -3.50% |       -1.88% |         18.64% |
| Net IR vs universe mean                  |  -0.1422 |      -0.0665 |         1.4543 |
| Net active max drawdown vs universe mean |  -28.51% |      -21.71% |        -18.63% |
| Net active annualized vs HS300 proxy     |    2.74% |        4.07% |         26.04% |
| Net IR vs HS300 proxy                    |   0.2340 |       0.2936 |         1.2697 |
| Net active max drawdown vs HS300 proxy   |  -31.94% |      -29.37% |        -23.96% |

### Top30

| Scheme         | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| -------------- | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Alpha158       |          0.97% |     0.1308 |      -40.60% |  199.02% |          -0.5956 |       -0.0792 |
| Risk factors   |          4.25% |     0.2472 |      -41.41% |  199.37% |          -0.4265 |        0.0822 |
| 3-day strategy |         29.30% |     1.0884 |      -25.53% |   40.03% |           1.4081 |        1.1909 |

### Top20 yearly annualized returns

| Year | Days | Alpha158 | Risk factors | 3-day strategy |
| ---- | ---: | -------: | -----------: | -------------: |
| 2023 |  242 |   -9.13% |      -10.06% |          9.71% |
| 2024 |  242 |    5.06% |       10.52% |         17.73% |
| 2025 |  243 |   48.57% |       56.63% |         72.52% |
| 2026 |  182 |   -9.31% |      -14.73% |         39.42% |

### Limits

This run evaluates the three fixed configurations, without candidate reselection or an independent confirmation window. Base/factor feature_fraction is 0.9/1.0, so differences do not isolate the added factors. 2026 is a partial year and fills use same-close quotes. All three backtests report `incomplete_market_data`; missing quotes can delay exits and retain stale marks.

### Reproduce

Fix one data snapshot; retain Task/Run IDs and wait for success before downstream submission. Use the same `--target` for remote commands. Run fixed-holding backtests once for base and once for factor predictions; use `qlib_a158_backtest` for the base model.

```bash
# Base model: 158 features
axonx submit --task qlib_a158_etl --input-dir '<same_data_snapshot>' --start-date 20150101 --end-date 20261008
axonx submit --task qlib_a158_train --source-tasks '<base_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 0.9 --random-seed 42 --num-threads 8
axonx submit --task qlib_a158_predict --source-tasks '<base_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# Final factor model: 158 base + 2 risk features
axonx submit --task qlib_factor_etl --input-dir '<same_data_snapshot>' --start-date 20150101 --end-date 20261008
axonx submit --task qlib_factor_train --source-tasks '<factor_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --context-groups risk --context-windows '[10]' \
  --feature-fraction 1.0 --random-seed 42 --num-threads 8
axonx submit --task qlib_factor_predict --source-tasks '<factor_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# Fixed holding: run once for base and once for factor predictions
axonx submit --task qlib_factor_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'

# Strategy version: reuse factor predictions with the selected 3-day policy
axonx submit --task qlib_strategy_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 3 \
  --replacement-fraction 0.2 --rank-buffer 1 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'
```

### Task provenance

Execution workspace: `/nas/jinli.yl/data/axon` on machine 45. Raw artifacts remain there; only this run group is listed.

| Stage             | Task ID                                                       | Run ID                             |
| ----------------- | ------------------------------------------------------------- | ---------------------------------- |
| base_etl          | `etl#qlib_a158_etl#fees-1010-base-etl`                        | `41fb603467ac4e78acc68294ae7d2699` |
| base_train        | `train#qlib_a158_train#fees-1010-base-train`                  | `eff2152ad9a244cb95a91f834e41a33a` |
| base_predict      | `predict#qlib_a158_predict#fees-1010-base-predict`            | `c9eaa50835004b9284897e5f2ad001e6` |
| base_backtest     | `backtest#qlib_a158_backtest#fees-1010-base-backtest`         | `b7ca108ed67a4ef4b38968f0770430bc` |
| factor_etl        | `etl#qlib_factor_etl#fees-1010-factor-etl`                    | `1d17d053b24b4e58b2175184372ea718` |
| factor_train      | `train#qlib_factor_train#fees-1010-factor-train`              | `c3ec05d4cbac4905b5603d9d6d2b07b1` |
| factor_predict    | `predict#qlib_factor_predict#fees-1010-factor-predict`        | `f541bb3b20eb406fb9dfb5c9c4f705a4` |
| factor_backtest   | `backtest#qlib_factor_backtest#fees-1010-factor-backtest`     | `3d0a9f5a718a4bb4a6f14873cad8e8ad` |
| strategy_backtest | `backtest#qlib_strategy_backtest#fees-1010-strategy-backtest` | `51c8cf5fca3d47cf95c6f4965e0c0302` |

| Shared input |                                                            SHA-256 |
| ------------ | -----------------------------------------------------------------: |
| market       | `5416cdf28fdd8bfb0280afa5d080fd7db0c6e50b82373cd024e910229c8dbc17` |
| calendar     | `b8048084ff1abafa81b97af01a58b7c8addf96fb061b7898127035e61408e731` |
| labels       | `52e832db44e3a961942c7d6e485b355378dea081c8b53ca34cf01aa2b1d0bda6` |

All backtests share these input digests; factor and strategy share predictions. Core/plugin versions: 0.1.1/0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0.
