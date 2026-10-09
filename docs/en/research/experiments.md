---
title: Experiment Design and Independent Confirmation
description: Fix controls, run ablations, lock a configuration, and evaluate evidence on an independent window.
---

# Experiment Design and Independent Confirmation

AxonX preserves execution evidence; experiment design determines which conclusions that evidence supports. This guide organizes a parameter or feature change into an inspectable comparison. Plugin documentation maintains specific algorithms and historical experiment numbers.

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

The current Qlib Factor experiment trains on `[20150101,20230101)` and selects groups using training-period validation RankIC, then reports a shared OOS interval from 2023. Qlib Strategy fixes the primary policy in advance and reports holding-period comparisons separately. Other experiment windows remain in the plugin archives.

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

Current experiment materials include the [experiment plan](../../../plugins/qlib_factor/DEVELOPMENT_PLAN_EN.md), [execution process](../../../plugins/qlib_factor/EXPERIMENT_PROCESS.md), [complete results](../../../plugins/qlib_factor/EXPERIMENT_RESULTS.md), and [validation material index](../../../plugins/qlib_factor/experiments/README.md). Summaries and validation materials are included in the repository; complete submission responses, raw logs, and daily Parquet files remain in the remote Task workspace. The reproduction guide supports new execution without promising access to unpublished historical data snapshots or artifacts.

## Report the conclusion

Report the baseline and locked configuration, selection process, independent window, metric changes, and uncertainty. Include failures, declining metrics, and limitations of trading assumptions. Task success establishes completed execution; the research conclusion still needs this evidence.
