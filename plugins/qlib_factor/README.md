# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` extends Alpha158 ETL with 13 optional market-moment, neutral-momentum and risk features, producing 171 feature columns. Training selects groups; the default `none` uses the 158 base features. The example below selects `risk` (160 features).

Training inherits cutoff-safe labels, early stopping on the final 10% of training dates and full-period refitting. Prediction and ordinary backtesting reuse the base plugin.

## Factors and timing

| Group    | Features | Definition                                                    |
| -------- | -------: | ------------------------------------------------------------- |
| mean     |        4 | Winsorized cross-sectional return mean: market direction      |
| variance |        4 | Winsorized cross-sectional sample variance: return dispersion |
| neutral  |        3 | Beta-adjusted momentum over 5/10/20 days                      |
| risk     |        2 | Residual volatility and downside risk over 20 days            |

Stock returns are adjusted C(T)/C(T−h)−1 for h=1/3/5/10 market trading days. Both endpoints must have quotes, positive volume, amount and adjusted prices. Price-limit stocks remain included; future labels and tradability are never consulted. For each date/horizon, winsorize at the linear 2%/98% quantiles, then calculate the equal-weight mean and sample variance (ddof=1). Empty pools remain null; singleton variance is null. Variance measures cross-sectional disagreement; near-zero mean alone does not establish that most stocks are range-bound.

Global moments are available after T close and shared by every stock that day; momentum/risk features vary by stock. Evaluate model ablations, since daily-constant factors have no cross-sectional IC. See [cross_section.py](axonx_qlib_factor/internal/cross_section.py); ETL saves daily values and horizon-specific pool counts.

`context_groups` accepts comma-separated `mean`, `variance`, `neutral`, `risk`, or `none`. The default remains `none`; the documented factor version explicitly uses `risk`. Unsupported groups and context columns fail validation.

`context_windows` selects a nonempty subset of `[1,3,5,10]`, defaulting to all four horizons. ETL publishes all 13 factors; context_windows filters only global mean/variance, while stock groups retain their fixed windows. Ablations reuse that dataset, and training metadata records the selected windows. For example, `--context-groups mean,variance --context-windows '[10]'` adds only two 10-day factors.

Beta uses the preceding 60 market dates through T−1, with at least 30 paired stock/market returns. Stock daily returns use contemporaneous 2%/98% winsorization; the market return is their equal-weight mean. Beta is covariance divided by market variance, clipped to [−3,3]; variance ≤1e−12 leaves it undefined. Neutral momentum subtracts prior beta times compounded market returns from the stock's 5/10/20-day return. Residual volatility is the 20-day sample standard deviation of stock return minus prior beta × market return; downside risk is sqrt(mean(min(stock return,0)²)). Both risk windows require 16 valid observations out of 20. All stock features remain null when the current quote is invalid.

## Install and run

Research plugins are not published to PyPI. Install the AxonX core and clone the repository; run the following commands from its root. For local Agent development, install in dependency order in the execution service's Python environment:

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
```

Restart persistent services after Python source changes; reinstall after dependency or entry-point metadata changes. Omit `-e` for fixed-version experiments. Deploy remotely with ordinary installation, installing upstream plugins in order on the same target service; configure `AXONX_TARGET_TOKEN` first and replace the example address below:

```bash
# Build the wheel and POST /upload first; use its returned absolute location.
axonx plugin install '<uploaded answer.location>' --target http://research.example:1024
# Build the wheel and POST /upload first; use its returned absolute location.
axonx plugin install '<uploaded answer.location>' --target http://research.example:1024
axonx get_task_definition --task qlib_factor_train --target http://research.example:1024

axonx exec --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx \
  --context-groups risk --feature-fraction 1.0 --target http://research.example:1024
axonx exec --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Save each returned Task ID and Run ID and wait for `succeeded` before submitting downstream work. `qlib_factor_analysis` is an optional diagnostic branch. Installation updates the selected Python environment without refreshing loaded service objects or tracking restart requirements. Restart a persistent service when it must reload schemas or contributions. New CLI processes load the installed environment; record Task/Run IDs and stop on installation or verification failures. [Qlib Alpha158](../qlib_a158/README.md)

## Experiments

Settings, full results and artifact provenance are maintained in the [research experiment guide](../../docs/en/research/alpha158-case.md). The three configurations were rerun on machine 45 with 0.05% buy / 0.15% sell fees.

AxonX owns protocol v1 in `axonx.task.protocol`, using the existing `TaskType` as `task_type`. Training exposes `output_params.protocol` and one `models.json` collection; member/checkpoint metadata sidecars are removed. Offline and online predictions share one `model_identity` (`models_sha256`, `features_sha256`), `dates`, `score_columns` and file revision (`size:mtime_ns`). Feature contracts, semantic fingerprints and verified model snapshots are shared AxonX helpers. Missing headers and old formats are rejected; regenerate artifacts. Package versions remain independent.

Backtests now publish **all market** (`all`) and **CSI 300** (`hs300`) as independent reports in one Task. Studio provides a universe dropdown, including independent selections in strategy comparison. Positive signal-time `index_weight_hs300` defines CSI 300 membership. The backtest schema uses `default_universe`, `universes` and a shared artifact registry; regenerate old backtests.
