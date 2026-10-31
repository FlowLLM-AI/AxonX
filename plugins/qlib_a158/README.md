# Qlib Alpha158 plugin

[English](README.md) · [简体中文](README_ZH.md) · [Plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management)

An AxonX offline research plugin built from the Qlib Alpha158 / LightGBM workflow, providing data processing, factor analysis, model training, out-of-sample prediction, portfolio construction, and TopN backtesting. Tasks consume prepared historical Parquet data.

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
| Strategy   | Portfolio-defined TopN policies; each `portfolio_id` records the strategy and parameters                                                    | Top50, at most 5 replacements, 95% cash allocation                              |
| Evaluation | Compound net equity, 252-day annualization; constituent-weighted HS300 proxy                                                                | Actual CSI300 index quotes; default arithmetic risk accumulation                |

Stage metadata records `qlib_reference` / `qlib_deviations` to track the reference version and workflow differences.

## Training parameters

Training defaults to `parameter_preset=axonx`. `--parameter-preset qlib` switches only hyperparameter defaults; labels, universe, seed, thread count, validation and refitting remain unchanged. Explicit values override the preset. Numeric training settings must be finite.

| Parameter                       | axonx   | qlib                |
| ------------------------------- | ------- | ------------------- |
| learning_rate                   | 0.03    | 0.2                 |
| num_leaves / max_depth          | 31 / -1 | 210 / 8             |
| feature_fraction                | 0.9     | 0.8879              |
| bagging_fraction / bagging_freq | 0.9 / 1 | 0.8789 / 0          |
| lambda_l1 / lambda_l2           | 0 / 0   | 205.6999 / 580.9768 |

Qlib aliases `colsample_bytree` / `subsample` map to `feature_fraction` / `bagging_fraction`. Its example leaves `subsample_freq` unset, so the `qlib` preset uses `bagging_freq=0`.

## Install and inspect

Plugin version 0.3.0 requires Python 3.12+ and AxonX `>=0.3.1`; Task execution supports macOS and Linux. Install into the Python environment that runs `axonx exec` (the service interpreter for `--target`). LightGBM, NumPy, and Polars are installed as dependencies.

This plugin is not published to PyPI. Clone the repository and install the matching core from its root, then install the plugin as a wheel:

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e .
axonx plugin install ./plugins/qlib_a158
axonx plugin list
axonx plugin show axonx-qlib-a158
```

For source development, run from the repository root:

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin inspect ./plugins/qlib_a158
```

Editable installation requires source in the selected Python environment and cannot use `--output`; with `--target`, the source directory belongs to that machine. New `exec` processes load current Python sources. Reinstall after dependency or entry-point changes, and restart persistent services to refresh their Task catalogs, schemas and loaded dependencies.

The local CLI environment may differ from the remote service environment. For remote deployment, configure the target service token and specify the target explicitly:

```bash
export AXONX_TARGET_TOKEN='<service token>'
axonx plugin build ./plugins/qlib_a158 --output /tmp/axonx-wheels
# Upload the actual wheel from /tmp/axonx-wheels before installation.
axonx plugin install '<uploaded answer.location>' --target 'http://<host>:1024' --client-timeout 600
axonx plugin list --target 'http://<host>:1024'
```

Installation modifies the selected interpreter. New CLI processes discover installed plugins; definition Jobs and Studio retain the service startup catalog until restart. Stop on installation or verification failures. [plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management)

After upload installation, discard the staged upload using its workspace-relative `path`; the installation source uses the absolute `location`. Restart with `axonx restart_service --target HOST:PORT`, wait for the service to return, and verify the installed version and Task definitions. The linked deployment guide includes upload, checksum verification and cleanup.

## Execution and configuration

`axonx exec` runs synchronously in the local CLI process and prints output parameters; its exit code determines command success. It can run without a service. With `--target`, the command runs in a CLI subprocess on that service. Definition, status and log Jobs require a running service and describe its environment and workspace.

Execution settings resolve in this order: explicit CLI options → service `get_config` → built-in defaults. Use `--workspace-dir /absolute/path` to select the research workspace explicitly. Relative ETL inputs resolve inside that workspace. Local and remote commands must use the same workspace as their upstream Tasks.

Use the standard application configuration. Installed `plugin.yaml` files contribute Task registrations; research inputs belong to `exec` options:

```bash
axonx app --workspace-dir /tmp/axonx-research
# In another terminal, with historical inputs already prepared there:
axonx exec --task qlib_a158_research --task-name baseline --workspace-dir /tmp/axonx-research
axonx status --task-id 'base#qlib_a158_research#baseline' --detail full
```

Task IDs use `<type>#<registration>#<task_name>`. Save both the ID and `started_at` from logs or full status; rerunning the same name replaces that Task's current outputs. Parent/child calls describe composition, while `upstream_task_ids` describes consumed data. Display replicas cannot be used as research inputs.

## Prepare data

Configure `AXONX_TUSHARE_TOKEN` in the execution service environment and use the built-in `download_tushare_task` to prepare Tushare Parquet data. The default ETL input is `tushare/` inside the workspace, rather than the current shell directory.

```bash
axonx exec --task download_tushare_task \
  --start-date 20140101 --end-date 20261008 \
  --datasets 'static,stk_limit,daily,adj_factor,index_weight'
```

`axonx exec` returns the final exit code. Continue with ETL after the download succeeds.

| Files                                                            | Purpose                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------------------------ |
| `*/*/daily.parquet`, `*/*/adj_factor.parquet`                    | Required market data and adjustment factors                        |
| `trade_cal.parquet`, `stock_basic.parquet`, `namechange.parquet` | Required trading calendar, stock master data, and historical names |
| `*/*/stk_limit.parquet`                                          | Official price limits used for tradability                         |
| `*/*/index_weight.parquet`                                       | CSI 300 weights used for index pools and benchmarks                |

`stock_basic.parquet` must include `ts_code`, `name`, `list_date` and `delist_date`; listed stocks may have a null delisting date. The built-in `download_tushare_task` requests these fields in its `static` group. Use `--days-back 14` for a recent 14-day refresh; the default groups also cover price limits, daily quotes, adjustment factors and index weights.

Prepare sufficient preceding history for rolling windows. The example trains from 2015, so downloads start in 2014. The default download only looks back seven calendar days and does not provide a full history. For credentials, partition layout, and updates, see [Tushare downloads](https://flowllm-ai.github.io/AxonX/en/research/tushare).

ETL reads the preceding market dates required by its longest rolling window. Earlier partitions outside that calculation window do not block the task; all participating quotes and adjustment factors remain strictly validated.

## Composed research

`qlib_a158_research` runs ETL → Train → Predict → Portfolio → Backtest as independently observable child Tasks. Supply `--analysis '{}'` to run factor analysis from the ETL output. Historical Tushare inputs must already exist.

```bash
axonx exec --task qlib_a158_research --task-name baseline \
  --etl '{"start_date":"20150101","end_date":"20261008"}' \
  --train '{"train_end":"20230101"}' \
  --predict '{"pred_end":"20261008"}' \
  --portfolio '{"top_ns":[5,10,20,30]}'
```

Prediction starts at the training cutoff when omitted. The plugin owns nested research inputs, child names and dependencies. Backtests end at the last signal by default; set `backtest.as_of_date` explicitly for later valuation or settlement. Leaf prediction accepts a Train and an optional compatible ETL, allowing saved models to score new datasets.

## Tasks and execution

| Task                  | Upstream              | Outputs                                                             |
| --------------------- | --------------------- | ------------------------------------------------------------------- |
| `qlib_a158_etl`       | Workspace market data | Features, labels, trading status, and statistics                    |
| `qlib_a158_analysis`  | ETL Task ID           | Factor diagnostics and analysis                                     |
| `qlib_a158_train`     | ETL Task ID           | Model, training protocol, validation curves, and feature importance |
| `qlib_a158_predict`   | Train + optional ETL  | Full-cross-section predictions and statistics                       |
| `qlib_a158_portfolio` | Predict Task ID       | Frozen portfolio plans, signal rankings, and strategy identities    |
| `qlib_a158_backtest`  | Portfolio Task ID     | Daily backtests, period summaries, and holding-related artifacts    |

Factor analysis branches from ETL and is not a prerequisite for training. Submit in the following order, record Task IDs from execution logs, and wait for each stage to succeed before submitting its downstream stage.

```bash
axonx exec --task qlib_a158_etl --start-date 20150101 --end-date 20261008

# After ETL succeeds
axonx exec --task qlib_a158_analysis --upstream-task-ids '["<etl_task_id>"]'
axonx exec --task qlib_a158_train --upstream-task-ids '["<etl_task_id>"]' \
  --train-start 20150101 --train-end 20230101

# After training succeeds
axonx exec --task qlib_a158_predict --upstream-task-ids '["<train_task_id>"]' \
  --pred-start 20230101 --pred-end 20261008

# After prediction succeeds
axonx exec --task qlib_a158_portfolio --upstream-task-ids '["<predict_task_id>"]' --top-ns '[5,10,20,30]'
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<portfolio_task_id>"]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

Inspect each Task's schema with `axonx get_task_def --task qlib_a158_train`. For remote execution, add the same `--target` to execution and definition commands and use the target service's Python environment.

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

Consult `get_task_def` in the execution environment for the complete parameter Schema.

## Features, labels, and backtest protocol

Original features use the `f_alpha158_*` namespace: 13 current-day price features and 29 rolling feature families over 5, 10, 20, 30, and 60 trading-day windows. Prices are adjusted, and trading-calendar and listing-status information are preserved.

ETL protocol version 1 publishes independent `dataset`, `labels`, `market`, and `calendar` artifacts. Raw labels use the next market date; suspended or missing quotes invalidate the label without searching for a future resumption. Training filters exclusive cutoffs and handles tails before computing `label_return_rank` or `label_return_csz`; fitting, validation and final training transform their own eligible reference rows. Rank uses average ranks scaled to `[0,1]`; CSZ uses clipped daily returns and population standard deviation (`ddof=0`). Early stopping selects rounds using validation L2. Prediction does not require future labels; its statistics describe scores and signal-time eligibility. Studio renders the configured TopN sizes and marks incomplete market-data results as provisional.

Backtesting inherits AxonX `BaseStockBacktestTask`, reads independent prices and trading states, and marks positions to market daily. Blocked exits retain capital; unfilled targets are not replaced by lower-ranked stocks. `buy_cost_rate=0.0005` and `sell_cost_rate=0.0015` default to the Qlib reference rates (0.05% buy / 0.15% sell); the normalized-cash ledger omits the RMB 5 minimum. Fees apply to executed notional; `top_ns` is an integer list. An optional `market_status_file` supplies confirmed suspensions (signal keys plus `market_status=suspended`); absent quotes are not inferred as suspension and affected runs report `incomplete_market_data`. Top30 contains signal targets; `positions`, `orders`, and `trades` record actual portfolio state.

For return, cost, IC, and holding definitions, see [Interpreting backtests](https://flowllm-ai.github.io/AxonX/en/research/backtest).

Required prediction columns, optional columns and metadata constraints are listed in the [prediction input contract](../../docs/en/reference/research-artifacts.md#prediction-inputs-for-stock-backtesting).

## Local validation

From the repository root, after installing development dependencies:

```bash
python -m pytest \
  plugins/qlib_a158/tests \
  tests/unit/test_stock_backtest.py tests/unit/test_documentation_contracts.py -q
```

These checks run the composed CPU research workflow, new-data prediction, feature protocol validation, label/preset comparisons and the shared stock ledger. Install all three research plugins to run the cross-plugin tests.

To compare labels and presets using an existing successful ETL, run the analysis Task. Its summary and comparison manifest stay in its Task directory; child stage identities are recorded in metadata:

```bash
axonx exec --task qlib_a158_compare --task-name preset-comparison \
  --workspace-dir /tmp/axonx-research --upstream-task-ids '["<etl_task_id>"]' --labels '["rank","csz"]'
```

The comparison uses the ordinary CLI execution settings and child Task lifecycle. Its `summary_stats.csv` and `comparison.json` record stage Task IDs, `started_at` and input revisions. Nested `train`, `predict` and `backtest` options reuse the corresponding stage parameters and defaults; `predict.pred_start` must be at or after `train.train_end`. The comparison owns child names, dependencies, training preset/label, and backtest inputs/cutoff; omit those nested options.

## Experiments

Shared settings, results, reproduction commands and Task provenance are maintained in the [Alpha158 improvement case](../../docs/en/research/alpha158-case.md). Artifact fields and universe reports follow the [shared protocol](../../docs/en/reference/research-artifacts.md).
