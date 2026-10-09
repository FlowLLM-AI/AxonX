# Alpha158 experiments: Top5 / 10 / 20 / 30

[English](HOLDING_PERIOD_RESULTS.md) · [简体中文](HOLDING_PERIOD_RESULTS_ZH.md)

Train 2015–2022; predict and backtest the entire 20230103–20261008 interval (909 market days). All comparisons reuse the same model, predictions, market, labels and calendar; their input SHA-256 values match. No model retraining or code change was made.

## Configuration

Source `51ad265`; stock protocol v2; 158 features; LightGBM 4.7.0, seed 42. After 2.5% daily return trimming on each tail, 5,838,557 rows were refit for 315 rounds. The final 10% of dates tune the round count (validation starts 20220316; RankIC 0.1078). Prediction has 4,635,759 rows / 4,400,089 eligible candidates; full-period IC 0.0529 and RankIC 0.0923. These one-day signal diagnostics are unchanged by the holding-period experiments.

Closing-price proxy, sells before buys, each target at most 1/N equity, no index restriction, no forced liquidation at the cutoff. Each executed buy/sell costs 0.2%; annual risk-free rate 1.2%, annualization 252 days. Only holding_days changes to 5 or 10; the fee-free one-day run is an attribution control.

## Returns after fees

| Holding | TopN | Net annualized | Net cumulative | Max drawdown | Net Sharpe | Daily turnover¹ |
| ------- | ---- | -------------- | -------------- | ------------ | ---------- | --------------- |
| 1 day   | 5    | -30.49%        | -73.06%        | -75.62%      | -1.027     | 199.19%         |
| 1 day   | 10   | -32.23%        | -75.42%        | -78.40%      | -1.217     | 198.79%         |
| 1 day   | 20   | -36.46%        | -80.52%        | -82.52%      | -1.535     | 198.95%         |
| 1 day   | 30   | -38.62%        | -82.81%        | -84.06%      | -1.692     | 199.08%         |
| 5 days  | 5    | -9.56%         | -30.41%        | -54.55%      | -0.201     | 39.06%          |
| 5 days  | 10   | -3.74%         | -12.85%        | -43.20%      | -0.035     | 39.38%          |
| 5 days  | 20   | 0.22%          | 0.79%          | -43.16%      | 0.096      | 39.61%          |
| 5 days  | 30   | 2.25%          | 8.36%          | -39.72%      | 0.169      | 39.69%          |
| 10 days | 5    | 8.61%          | 34.69%         | -41.73%      | 0.389      | 19.84%          |
| 10 days | 10   | 7.80%          | 31.11%         | -37.71%      | 0.370      | 19.87%          |
| 10 days | 20   | 16.39%         | 72.90%         | -28.59%      | 0.690      | 19.88%          |
| 10 days | 30   | 15.86%         | 70.07%         | -32.34%      | 0.681      | 19.89%          |

¹ Turnover = (executed buys + sells) / previous equity; replacing the entire portfolio is approximately 200%. Net Sharpe is derived from daily net returns with sample standard deviation and the compounded daily risk-free rate.

Ten-day holding has positive net annualized returns at all four portfolio sizes in this run; Top20 reaches +16.39% with −28.59% maximum drawdown. Five-day Top5/Top10 remain negative, while Top20/Top30 are near break-even. Lower turnover materially improves net results, but the longer horizon also changes return exposure; stability needs further evaluation.

## Fee attribution and turnover

| TopN | 1 day, 0.2% each side | 1 day, no fees | Annualized difference (pp) |
| ---- | --------------------- | -------------- | -------------------------- |
| 5    | -30.49%               | 89.48%         | 119.96                     |
| 10   | -32.23%               | 84.36%         | 116.59                     |
| 20   | -36.46%               | 72.96%         | 109.42                     |
| 30   | -38.62%               | 67.32%         | 105.95                     |

The fee-free control is a separate ledger simulation, not gross returns reconstructed by adding costs back. It quantifies fee impact under this execution model; it is not a feasible zero-cost strategy.

Mean daily cost / previous equity: 1 day: 0.398%–0.398%; 5 days: 0.078%–0.079%; 10 days: 0.040%–0.040%.

A five-day holding period reduces average turnover, but mostly trades in batches anchored to the first signal day; it does not impose a 20% daily replacement cap. A ten-day period is also a scheduled-holding experiment. Their maximum daily two-sided turnover is still approximately 199%–209%. The existing engine still sells a due position even if it remains in TopN, then may buy it again.

## Quality and interpretation

| Run            | Evaluation status      | Unfilled missing-data sells |
| -------------- | ---------------------- | --------------------------- |
| 1 day          | incomplete_market_data | 51                          |
| 5 days         | incomplete_market_data | 332                         |
| 10 days        | incomplete_market_data | 27                          |
| 1 day, no fees | incomplete_market_data | 51                          |

Missing quotes are not confirmed suspensions; stale marks are carried when quotes are missing. Blocked exits retain capital; unfilled entries are not replaced. Results with incomplete_market_data are provisional. All variants use the same snapshot, but different holdings encounter different gaps. These are exploratory comparisons over the full prediction interval, not independent tests of a strategy selected using that interval.

## Archive and next experiment

The repository retains this report; generated daily data, backtest outputs and run manifests are excluded.

For future comparisons, fix the overlap interval, training cutoff, input hashes, candidates, fees and execution rules. If market data is repaired, rerun every compared strategy on the repaired snapshot.

The independent sweep completed 150 policies and 600 TopN portfolios; fixed-duration daily replays matched the original framework with zero error. See [qlib_strategy](../qlib_strategy/README.md) for the registered implementation and the [three-layer record](THREE_LAYER_EXPERIMENTS.md) for comparisons.
