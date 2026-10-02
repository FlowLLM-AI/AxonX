---
title: Interpreting Backtest Results
description: Understand a158 target portfolios, actual-exit accounting, costs, and Studio display definitions.
---

# Interpreting Backtest Results

The backtest page reads `daily` and `summary` artifacts from successful Backtest Tasks to display returns, signal quality, target lists, and period statistics. This page describes the current a158 plugin. Check the `protocol` of other plugins first.

![Backtest accounting flow](../../figures/research/backtest-accounting.svg)

## Running a backtest

```bash
axonx submit --task a158_backtest --source-tasks '<Predict Task ID>' \
  --transaction-cost-rate 0.002 \
  --annual-risk-free-rate 0.012 --annualization-days 252
```

After submission, use the TaskHandle's `task_id` and `run_id` to wait for success, then open the Studio backtest page. Upstream inputs must pass a158 prediction-field and Boolean-type checks and declare `actual_return_unit=decimal`.

| Parameter                       | Default | Meaning                                                     |
| ------------------------------- | ------- | ----------------------------------------------------------- |
| `transaction_cost_rate`         | `0.002` | Transaction cost rate applied to turnover, in decimal units |
| `annual_risk_free_rate`         | `0.012` | Annual risk-free rate for risk-adjusted metrics             |
| `annualization_days`            | `252`   | Trading days per year used in plugin summaries              |
| `minimum_index_weight_coverage` | `0.90`  | Minimum weight coverage required for index benchmarks       |
| `index_codes`                   | `[]`    | Restricts candidate indices, for example `["hs300"]`        |

Portfolio sizes are currently fixed at Top 1, 2, 3, 5, 10, 15, 20, and 30; this plugin's inputs do not allow arbitrary sizes. Benchmark definitions come from metadata `dimensions.benchmarks`.

## Signals, entries, and exits

On each signal date, the plugin selects buyable candidates with finite scores and sorts by descending score, breaking ties with stable symbol ordering. When multiple index codes are configured, it uses candidates belonging to any specified index.

Each day simulates selling due old positions at the close, then attempts to buy that day's targets. New positions can exit no earlier than the next trading day, and capital remains in old positions until actual exit. Targets failing `entry_is_buyable` leave cash uninvested. A full portfolio, an already-held symbol, or insufficient capital also affects purchases.

Returns are booked on actual exit dates. Open positions remain on the books at principal cost. This is not equity marked to market daily and does not simulate after-hours queues, partial fills, or actual capital-release details. Delayed exits and unsettled positions can affect return interpretation for the full window.

## Daily return fields

Using `top30_` as an example:

| Field                     | Meaning                                                               |
| ------------------------- | --------------------------------------------------------------------- |
| `gross_return`            | Realized exit profit for the day / opening book equity                |
| `turnover`                | Greater of actual buy and sell principal for the day / opening equity |
| `transaction_cost`        | Cost rate multiplied by turnover                                      |
| `net_return`              | Gross return minus transaction costs                                  |
| `count`, `open_positions` | Number of positions not yet exited                                    |
| `delayed_open_positions`  | Positions still held because exit is delayed                          |
| `unsettled_positions`     | Positions without an exit date yet                                    |
| `exits`, `delayed_exits`  | Number of exits and delayed exits that day                            |
| `unfilled_entries`        | Targets failing the entry buyability check                            |

`daily.trade_date` is the backtest calendar date. Portfolio returns correspond to exits actually realized that day; IC corresponds to signal diagnostics for that date. Do not merge them into one transaction.

## Read the protocol before the return chart

These screenshots show existing backtest results in a remote workspace, using the English UI for charts and tables. The experiment's return values do not replace this page's explanation of the `a158` implementation. Return screenshots retain the plotting area; check specific series names in your own page legend.

![Backtest cumulative net return](../../figures/studio/backtest-net-return.png)

**Net return** shows the compounded trajectory after costs, useful for inspecting equity curves and drawdowns.

![Backtest accumulated gross return](../../figures/studio/backtest-gross-return.png)

**Gross return** sums daily gross returns. Its final value cannot be compared as equal to the plugin summary's compounded gross return.

Studio recalculates return charts from daily data in the selected range:

```text
Cumulative net return = ∏(1 + daily net return) − 1
Gross return chart    = Σ(daily gross return)
```

Two daily returns of `+10%` and `-10%` compound to `-1%`, while their sum is `0%`. This is a difference in calculation definitions, not two color schemes for the same value.

The plugin's `summary.parquet` uses compounded gross returns for `gross_cumulative_return`. The last value of Studio's accumulated gross-return curve therefore need not equal gross cumulative return in the summary table. Net charts and summaries both compound returns, but different windows can still produce differences.

Chart date sliders and start/end dates change the display window and means within that window. Summary tables use overall, year, quarter, and month rows generated in advance by the plugin; moving a slider does not automatically rerun it.

## Signal quality

![Backtest IC and RankIC moving averages](../../figures/studio/backtest-quality.png)

**Model quality** shows MA20 for IC and RankIC, along with daily means over the selected date range. Hover to read curve values for a date. Range means and moving-average curves are different statistics.

![Backtest NDCG moving averages](../../figures/studio/backtest-ndcg.png)

The NDCG panel shows ranking diagnostics and window means for Top 5, 10, 15, 20, and 30, helping inspect high-score target ranking quality. It does not replace execution costs or portfolio returns.

- `ic`: Pearson correlation between scores and returns on strictly valid single-day labels.
- `rank_ic`: Spearman correlation over the same strict label sample.
- `topN_ndcg`: a ranking diagnostic based on strictly valid single-day return relevance in the candidate cross-section.

Studio also displays a 20-row moving average, using available samples at the beginning. Missing and non-finite values are excluded; windows with fewer than 20 valid observations are not full 20-day statistics. High IC does not necessarily imply high returns after costs; execution constraints and costs change results.

## What the Top 30 table means

![Top 30 target prediction, return and weight](../../figures/studio/backtest-holdings.png)

This screenshot retains only Prediction, Return, and Weight columns. Returns appear empty when unavailable. Interpret weights and scores together with the target-list protocol.

The current frontend is hardcoded to read `top30_holdings`. The table supports sorting, updates with the chart cursor date, and can be locked or moved to the latest day.

This field is the signal-date Top 30 **target candidate list**, including stocks that could not be purchased that day. It is neither an actual position ledger nor a complete execution record for the user's selected Top N. Its `daily_return` comes from the target's eventual holding return, potentially spanning delayed exits. `weight` is a weight proxy in target details, not a weight in the actual capital ledger.

Even if `dimensions.holding_detail_top_n` describes another size, the current page still reads `top30_holdings`. Extension plugins cannot simply rename the field and expect the frontend to display arbitrary Top N automatically.

## Summary metrics

![Backtest overall summary](../../figures/studio/backtest-overall.png)

Basic signal metrics in **Overall** are independent of portfolio size; Top N return metrics appear in their corresponding detail sections.

| Metric                | a158 summary definition                                                                             |
| --------------------- | --------------------------------------------------------------------------------------------------- |
| Cumulative net return | Compounded daily net returns                                                                        |
| Annualized net return | Cumulative equity annualized using observed days and annual trading days                            |
| Annualized volatility | Sample standard deviation of daily net returns multiplied by the square root of annual trading days |
| Maximum drawdown      | Peak drawdown of the compounded net equity curve including initial equity of 1, negative            |
| Win rate              | Proportion of days with positive net return; zero-return days are not wins                          |
| Average turnover      | Mean daily turnover                                                                                 |
| Gross Sharpe          | Mean/sample standard deviation of gross returns minus daily risk-free return, annualized            |
| Benchmark IR          | Mean/sample standard deviation of gross returns minus benchmark returns, annualized                 |
| ICIR / RankICIR       | Mean/sample standard deviation of the corresponding daily correlations, annualized                  |

Benchmarks may be empty when index weight coverage is insufficient; risk-adjusted metrics may also be missing. The `universe` benchmark is the mean return of candidates satisfying return conditions within the plugin's universe. Do not call it an exchange-wide market index.

## Yearly, quarterly, and monthly observations

![Backtest yearly summary](../../figures/studio/backtest-yearly.png)

**Yearly** shows both yearly signal metrics and return metrics for the selected Top N. Check each year's observed days before comparing annualized returns, volatility, and drawdowns.

![Backtest quarterly summary](../../figures/studio/backtest-quarterly.png)

**Quarterly** splits the range into quarters to locate where changes concentrate. Rows come from plugin-generated quarterly summaries.

![Backtest monthly summary](../../figures/studio/backtest-monthly.png)

**Monthly** helps check signal stability month by month. The table supports scrolling and sorting. Ratios may fluctuate more with smaller monthly samples.

## When results look abnormal

First verify prediction returns are in decimal units, then check date ranges, candidate size, costs, delayed exits, and unsettled positions. Create a new experiment Task when changing parameters. Changing Top N or the window on the page only changes observation and does not rerun the backtest.

## Related documentation and implementation

- [Strategy comparison](strategy-comparison.md), [Research artifact protocol](../reference/research-artifacts.md)
- [Plugin backtest protocol](../../../plugins/a158/axonx_alpha158/backtest.py)
- [Backtest accounting and summaries](../../../plugins/a158/axonx_alpha158/internal/backtest.py)
- [Studio backtest display](../../../axonx_studio/src/features/research/backtest/BacktestView.tsx)
