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
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --transaction-cost-rate 0.001 --target http://research.example:1024
```

Reuse successful base or factor predictions. Record returned Task / Run IDs and wait for success before reading results. Upstream `qlib_strategy_etl`, `qlib_strategy_analysis`, `qlib_strategy_train` and `qlib_strategy_predict` register factor-layer implementations; policy comparisons reuse predictions. Task-only wheel updates through the remote installation Job apply without restarting; restart when `restart_required` is true and verify Task definitions. Direct pip/source changes require restart. Install the AxonX core from this checkout together with the plugins.

<a id="experiments"></a>

## Final experiment settings and results

This section records this plugin’s final experiment. See the [three-version comparison](../../docs/en/research/experiments.md#comparison) for cross-plugin results. Metrics come from successful machine-45 Tasks and their metadata, summary.parquet, daily.parquet and trades.parquet; original artifacts remain in the execution workspace.

### Version configuration

Reuse factor-model predictions; minimum_holding_days=3, replacement_fraction=0.2, rank_buffer=1; no retraining.

Data, training windows, filtering, execution, and fee settings are maintained in the [three-version comparison](../../docs/en/research/experiments.md#comparison).

The model uses 160 features and refits the full training period after early stopping selects 426 rounds. Validation RankIC is 0.11321.

Freeze upstream stock_risk prediction `predict#qlib_factor_predict#2026100917Z7Ys`; factor definitions are maintained in [Qlib Factor](../qlib_factor/README.md#experiments). This version uses a 3-day minimum and the rank-retention rules above, with 4/6 fills per side daily for Top20/Top30.

The 3-day candidate has better net annualized return, net Sharpe, and drawdown, so it is the sole strategy version shown. This is exploratory selection on a reused development window, without independent confirmation. The minimum holding default remains 10 days; reproduce these results by explicitly passing 3.

### Metric definitions

Shared definitions for IC/RankIC, net returns, Sharpe, turnover, and active metrics are maintained in the [experiment comparison](../../docs/en/research/experiments.md#comparison). Portfolio metrics use 909 dates; active metrics use 908 benchmark-valid dates.

### Overall signals and full Top20 results

| Metric                                   | Strategy: 3d |
| ---------------------------------------- | -----------: |
| Overall IC                               |       0.0545 |
| Overall RankIC                           |       0.0966 |
| Overall RankICIR (annualized)            |      14.2859 |
| Net annualized                           |       32.36% |
| Net cumulative return                    |      174.92% |
| Net Sharpe                               |       1.1571 |
| Net annualized volatility                |       26.19% |
| Max drawdown                             |      -24.91% |
| Daily return win rate                    |       55.89% |
| Mean daily two-sided turnover            |       40.02% |
| Mean daily cost / prior equity           |      0.0400% |
| Closed trades                            |        3,624 |
| Net active annualized vs universe mean   |       18.65% |
| Net IR vs universe mean                  |       1.4547 |
| Net active max drawdown vs universe mean |      -18.63% |
| Net active annualized vs HS300 proxy     |       26.04% |
| Net IR vs HS300 proxy                    |       1.2699 |
| Net active max drawdown vs HS300 proxy   |      -23.96% |

### Top30 results

| Scheme       | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| ------------ | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Strategy: 3d |         29.29% |     1.0880 |      -25.53% |   40.03% |           1.4086 |        1.1912 |

### Top20 yearly results

| Year | Days | Strategy: 3d |
| ---- | ---: | -----------: |
| 2023 |  242 |        9.65% |
| 2024 |  242 |       17.73% |
| 2025 |  243 |       72.54% |
| 2026 |  182 |       39.43% |

Yearly values are interval net annualized returns; 2026 ends October 8. Results report `incomplete_market_data`: missing quotes may delay exits and carry stale marks. Same-close fills are a proxy. The 3-day scheme is exploratory on a reused development window, without independent confirmation; the default remains 10 days.

### Reproduce the experiment

Save Task/Run IDs and wait for success before each downstream submission; use the same `--target` for remote commands. Parameters below match the Setting table; verify remaining defaults with `get_task_definition` before submission.

```bash
axonx submit --task qlib_strategy_backtest --source-tasks '<stock_risk_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 3 \
  --replacement-fraction 0.2 --rank-buffer 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<market_path>' --calendar-file '<calendar_path>' --labels-file '<labels_path>'
```

### Task provenance and input checks

Execution workspace: `/nas/jinli.yl/data/axon` on machine 45.

| Stage / scheme         | Task ID                                          | Run ID                             |
| ---------------------- | ------------------------------------------------ | ---------------------------------- |
| Strategy: 3d: backtest | `backtest#qlib_strategy_backtest#2026100918JP6A` | `6e7306c9d9a54cdeb6c2aee6a36bd73d` |

| Input    | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

Core/plugin versions: 0.1.1 / 0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0. New data do not guarantee reproduction of the unpublished historical snapshot; raw artifacts are not committed.
