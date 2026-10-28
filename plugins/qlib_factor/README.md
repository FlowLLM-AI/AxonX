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

Plugin version 0.3.0 requires Python 3.12+, AxonX `>=0.3.0` and upstream research plugins `>=0.3.0`. Install the layers in dependency order. Research artifacts use protocol v1.

## Install and run

Research plugins are not published to PyPI. Clone the repository and install the AxonX 0.3.0 core (`pip install -e .` from its root); run the following commands from its root. For local Agent development, install in dependency order in the execution service's Python environment:

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
```

New `exec` processes load current Python sources. Reinstall after dependency or entry-point changes, and restart persistent services to refresh their Task catalogs, schemas and loaded dependencies. Omit `-e` for fixed-version experiments. Deploy remotely with ordinary installation, installing upstream plugins in order on the same target service; configure `AXONX_TARGET_TOKEN` first and replace the example address below:

```bash
axonx plugin build ./plugins/qlib_a158 --output /tmp/axonx-wheels
axonx plugin build ./plugins/qlib_factor --output /tmp/axonx-wheels
# Upload each actual wheel to POST /upload, then install in the order above.
axonx plugin install '<qlib_a158 upload.location>' --target http://research.example:1024 --client-timeout 600
axonx plugin install '<qlib_factor upload.location>' --target http://research.example:1024 --client-timeout 600
axonx get_task_def --task qlib_factor_train --target http://research.example:1024

axonx exec --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_train --upstream-task-ids '["<etl_task_id>"]' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx \
  --context-groups risk --feature-fraction 1.0 --target http://research.example:1024
axonx exec --task qlib_factor_predict --upstream-task-ids '["<train_task_id>"]' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_backtest --upstream-task-ids '["<predict_task_id>"]' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Record each Task ID and `started_at` from execution logs or `status --detail full`; continue only after a zero exit code and `succeeded` state. `qlib_factor_analysis` is an optional diagnostic branch. Installation modifies the selected interpreter. New CLI processes discover installed plugins; definition Jobs and Studio retain the service startup catalog until restart. Stop on installation or verification failures. [Qlib Alpha158](../qlib_a158/README.md)

After each installation, discard its staged upload using the returned workspace-relative `path`. Remote source paths refer to the target machine. Restart the persistent service after all layers are installed and verify definitions; see the complete [upload, verification and cleanup workflow](../../docs/en/plugins/management.md#deploy-remotely).

## Execution and configuration

`exec` runs synchronously in a fresh local CLI process. `--target` forwards it to a CLI subprocess on that service; commands return the Task exit code. Execution settings resolve as CLI options → service `get_config` → built-in defaults. Use `--workspace-dir /absolute/path` consistently for market data and upstream Tasks. Definition and status Jobs require a running service. Same-name reruns replace outputs; record both Task ID and `started_at`. Display replicas cannot be research inputs.

Start the optional inherited application configuration with `axonx app --config qlib_factor`. Its YAML contains only `extends: default`; installed `plugin.yaml` files contribute registrations. Supply dates, feature groups and model settings to each Task. The available registrations are `qlib_factor_etl`, `qlib_factor_analysis`, `qlib_factor_train`, `qlib_factor_predict` and `qlib_factor_backtest`. Prediction accepts a Train and an optional compatible ETL to score new data.

## Local validation

From the repository root, with all three research plugins and development dependencies installed:

```bash
python -m pytest plugins/qlib_factor/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

The research tests execute the factor and strategy chains against temporary synthetic market data, including artifact exchange and explicit prediction ETL selection.

## Experiments

Settings, full results and artifact provenance are maintained in the [research experiment guide](../../docs/en/research/alpha158-case.md). The three configurations were rerun on machine 45 with 0.05% buy / 0.15% sell fees.

AxonX owns protocol v1 in `axonx.task.models.artifacts`, with `TaskType` as `task_type` and task-relative artifact records (`path`, `size`, `revision`). Revisions use `size:mtime_ns`; they are file versions, not content checksums. Training publishes `output_params.protocol` and a `models.json` collection. Prediction snapshots model members and pins upstream artifacts through `axonx.task.storage.inputs`. Feature semantics and fingerprints belong to `axonx_qlib_a158.internal.protocol`; training, analysis and prediction validate this contract before consuming data. Prediction publishes `model_identity`, `dates`, `score_columns` and its file revision. Consumers require protocol headers and matching feature semantics.

Backtests publish **all market** (`all`) and **CSI 300** (`hs300`) as independent reports in one Task. Studio provides a universe dropdown, including independent selections in strategy comparison. Positive signal-time `index_weight_hs300` defines CSI 300 membership. The backtest schema uses `default_universe`, `universes` and a shared artifact registry.
