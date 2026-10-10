---
title: Interpreting Backtest Results
description: Shared stock protocols, cutoff-safe labels, daily valuation and portfolio artifacts.
---

# Interpreting Backtest Results

Alpha158 and enhanced Alpha158 use the same `BaseStockBacktestTask` and position ledger. Stock schema version 2 separates signal-time features, fixed-day labels and market data.

The shared implementation lives in `axonx.task.builtins.stock`; new plugins should import from this package.

![Stock backtest signals and daily equity accounting](../../figures/research/backtest-accounting.svg)

## Data contracts

ETL publishes four independent artifacts:

| Artifact   | Meaning                                                                                         |
| ---------- | ----------------------------------------------------------------------------------------------- |
| `dataset`  | Signal-time features, eligibility, reference price and adjustment factor                        |
| `labels`   | Raw decimal return to the next market date at the same time, target date and availability state |
| `market`   | Independent quotes, adjustment factors, buy/sell proxies and market status                      |
| `calendar` | Market trading dates, including dates without eligible predictions                              |

Keys are `trade_date` (YYYYMMDD string), `trade_time` (HHMM string), and `ts_code`. Labels never remove feature rows or prediction candidates. A suspension invalidates the corresponding fixed-day label; it does not substitute a later resumption return. Training computes rank/CSZ only after filtering the exclusive cutoff, selecting eligible rows and handling tails. Temporal fitting and validation use their own reference samples.

`market_status` is `quoted`, `suspended`, or `missing_data`. ETL can consume a separate `market_status_file` with the keys and explicit suspension/missing states. Absent quotes are not evidence of suspension. Confirmed signal-day suspension or missing status disables signal buyability even if a stale quote remains; model candidate rows are retained.

## Inputs

For required prediction columns, optional columns and metadata requirements, see [Prediction inputs for stock backtesting](../reference/research-artifacts.md#prediction-inputs-for-stock-backtesting).

```bash
axonx submit --task qlib_a158_backtest --source-tasks '<Predict Task ID>' \
  --top-ns '[1,5,10,30]' --holding-days 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

Source tasks resolve market, calendar and label artifacts. Explicit files use `input_file`, `market_file`, `calendar_file` and optional `labels_file`. `as_of_date` is the inclusive evaluation cutoff, defaulting to the latest market date. `top_ns` is an integer list; each size has an independent portfolio. Calendar dates must be valid YYYYMMDD values without nulls or duplicates; malformed calendars are rejected before computing label or holding horizons.

| Parameter                       | Default  | Meaning                                          |
| ------------------------------- | -------- | ------------------------------------------------ |
| `holding_days`                  | `1`      | Planned holding period in market days            |
| `buy_cost_rate`                 | `0.0005` | Fee on executed buy notional                     |
| `sell_cost_rate`                | `0.0015` | Fee on executed sell notional                    |
| `annual_risk_free_rate`         | `0.012`  | Annual risk-free rate                            |
| `annualization_days`            | `252`    | Trading dates per year                           |
| `minimum_index_weight_coverage` | `0.98`   | Required coverage for weighted benchmark proxies |
| `index_codes`                   | `[]`     | Optional signal candidate index restriction      |

The defaults match the Qlib reference: `--buy-cost-rate 0.0005 --sell-cost-rate 0.0015` (0.05% on buys and 0.15% on sells). An explicit `0` makes that side free. Fees apply to executed notional; normalized-cash backtests do not impose a minimum monetary fee.

## Execution and valuation

Signals rank by score descending, then symbol ascending. Selection does not consult future labels. The engine marks existing positions, attempts due sells, and then funds same-day targets from available cash. An unfilled target is not replaced by a lower-ranked stock. Already-held stocks, position capacity and available cash constrain new purchases.

A blocked exit retains both its position and its capital. Confirmed suspension carries the last reliable adjusted-price mark; a later quoted date updates valuation and permits another exit attempt. Missing data affecting held or selected stocks sets `evaluation_status=incomplete_market_data`; the provisional result remains inspectable. No position is forcibly liquidated at the cutoff.

`missing_market_as_suspension=true` temporarily treats absent quotes and explicit `missing_data` as suspensions during backtesting. It retains the last mark, blocks trading and does not mark the evaluation incomplete for those gaps. This assumption is recorded in task inputs; it does not rewrite market artifacts or labels. The shared default is `false`. TODO: integrate independently sourced suspension intervals to distinguish suspensions from data gaps.

The same-time quote is an execution proxy. It does not guarantee that a signal computed after a bar or closing auction can fill at that price, nor model queues or partial fills. Inspect the stored execution protocol before interpreting results as a tradable strategy.

```text
Equity = cash + marked position value
Daily net return = equity / previous equity - 1
Daily cost = executed buy and sell costs / previous equity
Daily gross return = daily net return + daily cost
Turnover = executed buy and sell notional / previous equity
```

Adjusted-price units preserve value across corporate-action price changes. Marked gains are not booked again on exit. Costs apply to the initial purchase as well as later trades.

## Outputs

| Artifact    | Meaning                                                                       |
| ----------- | ----------------------------------------------------------------------------- |
| `daily`     | Calendar-aligned returns, equity, cash, open positions and signal diagnostics |
| `summary`   | Overall, yearly, quarterly and monthly statistics                             |
| `targets`   | Signal-selected candidates                                                    |
| `orders`    | Actual fills and unfilled reasons                                             |
| `positions` | Actual daily holdings, adjusted units, weights and market values              |
| `trades`    | Completed holding periods, actual entry/exit prices, returns and fees         |

`daily` retains `topN_*` columns and `dimensions` describes available portfolio sizes and benchmarks. `top30_holdings` is a signal target list; it is not the actual position book. Use `positions` for actual exposure. Unfinished positions remain in that artifact even when no completed trade exists.

## Signal diagnostics and benchmarks

IC, RankIC and NDCG use the same signal-day buyable candidate pool as target selection, including the `index_codes` restriction. IC and RankIC compare scores with valid fixed-one-market-day raw returns. NDCG measures top-ranked signal quality against the same available return sample; missing labels do not refill the selected ranking. These diagnostics belong to the signal date. Returns and valuation belong to the portfolio calendar date.

`benchmark_universe_return` is an available-signal cross-section mean. `index_weight_*` produces weighted return proxies only when coverage meets the configured threshold. They are not official total-return index series. Benchmark returns use the label target date, so their period aligns with portfolio valuation.

Studio reads `daily`, `summary` and `dimensions`. Net-return charts compound daily net returns, while the accumulated-gross chart sums daily gross returns; the latter need not equal compounded gross return in the summary. Period tables are task-generated and do not automatically rerun when the chart range changes.

Studio derives return and NDCG series from `dimensions.top_ns`, displays incomplete market-data evaluations as provisional, and exposes all portfolio artifacts. Prediction statistics describe signal-time scores and eligibility; schema version 2 does not embed future returns or valid-return coverage in predictions. Empty statistics and missing labels display as unavailable.
