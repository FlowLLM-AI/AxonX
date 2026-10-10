# Qlib Alpha158 plugin

[English](README.md) · [简体中文](README_ZH.md) · [Plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management)

An AxonX research plugin built from the Qlib Alpha158 / LightGBM workflow, providing data processing, factor analysis, model training, out-of-sample prediction, and TopN backtesting.

Uses 158 price and volume features as a research baseline. For context features and ablation experiments, see [Qlib Factor](../qlib_factor/README.md).

## Differences from original Qlib

The plugin combines Alpha158 features, daily cross-sectional labels and LightGBM with AxonX data, training, prediction and backtest Tasks. The example at Qlib commit `54355232463878d2eebb91fe0ee5fa7fa1f5976c` serves as the research reference. The table describes the scheme and its differences:

| Stage      | This plugin                                                                                                                                 | Original Qlib example                                                           |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Universe   | Shanghai/Shenzhen stocks excluding Beijing; signal-buyable training rows                                                                    | Historical CSI300 members                                                       |
| Features   | Same 158 features/windows; extrema indices skip absent quotes; near-zero correlations are invalid; regression preserves trading-day offsets | Alpha158 expression operators                                                   |
| Data       | Tushare adjusted prices and volume                                                                                                          | Qlib snapshot and collector normalization                                       |
| Labels     | T→T+1 close return, daily rank by default, 2.5% trimming per tail                                                                           | T+1→T+2 close return, DropnaLabel + sample-std CSZScoreNorm                     |
| Training   | Last 10% of dates select rounds, then refit all training dates; purge cutoff-crossing labels                                                | Independent train/valid/test, retain early-stopped model                        |
| Trading    | Same-close quote proxy, official limits with board-specific fallback, 0.05% buy / 0.15% sell by default                                     | Next-close execution, uniform 9.5% threshold, 0.05% buy / 0.15% sell, minimum 5 |
| Strategy   | Fixed holding expiry TopN; retention remains in the strategy plugin                                                                         | Top50, at most 5 replacements, 95% cash allocation                              |
| Evaluation | Compound net equity, 252-day annualization; constituent-weighted HS300 proxy                                                                | Actual CSI300 index quotes; default arithmetic risk accumulation                |

Stage metadata records `qlib_reference` / `qlib_deviations` to track the reference version and workflow differences.

## Training parameters

Training defaults to `parameter_preset=axonx`. `--parameter-preset qlib` switches only hyperparameter defaults; labels, universe, seed, thread count, validation and refitting remain unchanged. Explicit values override the preset.

| Parameter                       | axonx   | qlib                |
| ------------------------------- | ------- | ------------------- |
| learning_rate                   | 0.03    | 0.2                 |
| num_leaves / max_depth          | 31 / -1 | 210 / 8             |
| feature_fraction                | 0.9     | 0.8879              |
| bagging_fraction / bagging_freq | 0.9 / 1 | 0.8789 / 0          |
| lambda_l1 / lambda_l2           | 0 / 0   | 205.6999 / 580.9768 |

Qlib aliases `colsample_bytree` / `subsample` map to `feature_fraction` / `bagging_fraction`. Its example leaves `subsample_freq` unset, so the `qlib` preset uses `bagging_freq=0`.

## Install and inspect

Requires Python 3.12+ and AxonX `>=0.1.1,<0.2`; local Task execution supports macOS and Linux. Install into the execution service’s Python environment, then restart the service to reload contributions. LightGBM, NumPy, and Polars are installed as dependencies.

```bash
pip install axonx-qlib-a158
axonx plugin list
axonx plugin show axonx-qlib-a158
```

For source development, run from the repository root:

```bash
pip install -e ./plugins/qlib_a158
axonx plugin inspect ./plugins/qlib_a158
```

The local CLI environment may differ from the remote service environment. For remote deployment, configure the target service token and specify the target explicitly:

```bash
export AXONX_TARGET_TOKEN='<service token>'
axonx plugin install ./plugins/qlib_a158 --target 'http://<host>:1024'
axonx plugin list --target 'http://<host>:1024'
```

Task-only wheel updates through the remote installation Job refresh subsequent Task queries and submissions without restarting. Restart when `restart_required` is true, then query Task definitions to verify the fields. Direct `pip install` and editable source changes require a service restart. Install the AxonX core from this checkout together with the plugins. See [plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management).

## Prepare data

Configure `AXONX_TUSHARE_TOKEN` in the execution service environment and use the built-in `download_tushare_task` to prepare Tushare Parquet data. The default ETL input is `tushare/` inside the workspace, rather than the current shell directory.

```bash
axonx submit --task download_tushare_task \
  --start-date 20140101 --end-date 20261008 \
  --datasets 'static,stk_limit,daily,adj_factor,index_weight'
```

Save the returned `task_id` and `run_id`, and wait for the download to succeed before submitting ETL:

```bash
axonx --client-timeout 86400 wait_task \
  --task-id '<download_task_id>' --run-id '<download_run_id>'
```

| Files                                                            | Purpose                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------------------------ |
| `*/*/daily.parquet`, `*/*/adj_factor.parquet`                    | Required market data and adjustment factors                        |
| `trade_cal.parquet`, `stock_basic.parquet`, `namechange.parquet` | Required trading calendar, stock master data, and historical names |
| `*/*/stk_limit.parquet`                                          | Official price limits used for tradability                         |
| `*/*/index_weight.parquet`                                       | CSI 300 weights used for index pools and benchmarks                |

`stock_basic.parquet` must include `ts_code`, `name`, `list_date` and `delist_date`; listed stocks may have a null delisting date. The built-in `download_tushare_task` requests these fields in its `static` group. Use `--days-back 14` for a recent 14-day refresh; the default groups also cover price limits, daily quotes, adjustment factors and index weights.

Prepare sufficient preceding history for rolling windows. The example trains from 2015, so downloads start in 2014. The default download only looks back seven calendar days and does not provide a full history. For credentials, partition layout, and updates, see [Tushare downloads](https://flowllm-ai.github.io/AxonX/en/research/tushare).

ETL reads the preceding market dates required by its longest rolling window. Earlier partitions outside that calculation window do not block the task; all participating quotes and adjustment factors remain strictly validated.

## Tasks and execution

| Task                 | Upstream              | Outputs                                                             |
| -------------------- | --------------------- | ------------------------------------------------------------------- |
| `qlib_a158_etl`      | Workspace market data | Features, labels, trading status, and statistics                    |
| `qlib_a158_factor`   | ETL Task ID           | Factor diagnostics and analysis                                     |
| `qlib_a158_train`    | ETL Task ID           | Model, training protocol, validation curves, and feature importance |
| `qlib_a158_predict`  | Train Task ID         | Full-cross-section predictions and statistics                       |
| `qlib_a158_backtest` | Predict Task ID       | Daily backtests, period summaries, and holding-related artifacts    |

Factor analysis branches from ETL and is not a prerequisite for training. Submit in the following order, use the actual returned Task IDs, and wait for each stage to succeed before submitting its downstream stage.

```bash
axonx submit --task qlib_a158_etl --start-date 20150101 --end-date 20261008

# After ETL succeeds
axonx submit --task qlib_a158_factor --source-tasks '<etl_task_id>'
axonx submit --task qlib_a158_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101

# After training succeeds
axonx submit --task qlib_a158_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# After prediction succeeds
axonx submit --task qlib_a158_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

For every wait, provide both identifiers from that submission:

```bash
axonx --client-timeout 86400 wait_task \
  --task-id '<task_id>' --run-id '<run_id>'
axonx get_task_definition --task qlib_a158_train
```

For remote execution, add the same `--target` to all submission, wait, and definition queries. Install and execute against the same service environment.

## Key parameters

| Stage / parameter                                 | Default                 | Meaning                                                         |
| ------------------------------------------------- | ----------------------- | --------------------------------------------------------------- |
| ETL `start_date` / `end_date`                     | `20140101` / null       | First / last output dates, inclusive                            |
| ETL `min_history_coverage`                        | `0.8`                   | Minimum history coverage for rolling features                   |
| Train `train_start` / `train_end`                 | `20150101` / `20230101` | Inclusive start, exclusive cutoff                               |
| Train `label_column`                              | `label_return_rank`     | Daily cross-sectional return rank target                        |
| Train `label_winsorize_tail`                      | `0.025`                 | Each tail clipped before training-only CSZ normalization        |
| Train `trim_tail`                                 | `0.025`                 | Remove 2.5% of raw returns from each daily tail                 |
| Train `validation_ratio`                          | `0.10`                  | Last training dates reserved for internal validation            |
| Train `num_boost_round` / `early_stopping_rounds` | `1000` / `50`           | Maximum rounds / early stopping patience                        |
| Train `random_seed`                               | `42`                    | Model sampling seed                                             |
| Predict `pred_start` / `pred_end`                 | `20230101` / null       | Prediction interval; start must not precede the training cutoff |
| Backtest `buy_cost_rate`                          | `0.0005`                | Fee on executed buy notional                                    |
| Backtest `sell_cost_rate`                         | `0.0015`                | Fee on executed sell notional                                   |
| Backtest `annualization_days`                     | `252`                   | Trading days used for annualization                             |

Consult `get_task_definition` in the execution environment for the complete parameter Schema.

## Features, labels, and backtest protocol

Original features use the `f_alpha158_*` namespace: 13 current-day price features and 29 rolling feature families over 5, 10, 20, 30, and 60 trading-day windows. Prices are adjusted, and trading-calendar and listing-status information are preserved.

ETL schema version 2 publishes independent `dataset`, `labels`, `market`, and `calendar` artifacts. Raw labels use the next market date; suspended or missing quotes invalidate the label without searching for a future resumption. Training filters exclusive cutoffs and handles tails before computing `label_return_rank` or `label_return_csz`; fitting, validation and final training transform their own eligible reference rows. Rank uses average ranks scaled to `[0,1]`; CSZ uses clipped daily returns and population standard deviation (`ddof=0`). Early stopping selects rounds using validation L2. Prediction does not require future labels; its statistics describe scores and signal-time eligibility. Studio renders the configured TopN sizes and marks incomplete market-data results as provisional.

Backtesting inherits AxonX `BaseStockBacktestTask`, reads independent prices and trading states, and marks positions to market daily. Blocked exits retain capital; unfilled targets are not replaced by lower-ranked stocks. `buy_cost_rate=0.0005` and `sell_cost_rate=0.0015` default to the Qlib reference rates (0.05% buy / 0.15% sell); the normalized-cash ledger omits the RMB 5 minimum. Fees apply to executed notional; `top_ns` is an integer list. An optional `market_status_file` supplies confirmed suspensions (signal keys plus `market_status=suspended`); absent quotes are not inferred as suspension and affected runs report `incomplete_market_data`. Top30 contains signal targets; `positions`, `orders`, and `trades` record actual portfolio state.

For return, cost, IC, and holding definitions, see [Interpreting backtests](https://flowllm-ai.github.io/AxonX/en/research/backtest).

Required prediction columns, optional columns and metadata constraints are listed in the [prediction input contract](../../docs/en/reference/research-artifacts.md#prediction-inputs-for-stock-backtesting).

## Local validation

From the repository root, after installing development dependencies:

```bash
python -m pytest \
  tests/unit/test_qlib_a158.py tests/unit/test_alpha158_labels.py tests/unit/test_alpha158_backtest.py \
  tests/unit/test_stock_backtest.py tests/unit/test_stock_pipeline.py -q
```

These checks cover feature boundaries, label timing, four-way parameter comparisons, side fees, delayed exits and cash/position accounting.

## Experiments

Settings, full results and artifact provenance are maintained in the [research experiment guide](../../docs/en/research/experiments.md#comparison). The three configurations were rerun on machine 45 with 0.05% buy / 0.15% sell fees.
