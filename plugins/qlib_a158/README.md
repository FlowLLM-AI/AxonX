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
| Trading    | Same-close quote proxy, official limits with board-specific fallback, 0.2% per executed side by default, with separate buy/sell rates       | Next-close execution, uniform 9.5% threshold, 0.05% buy / 0.15% sell, minimum 5 |
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

## Parameter experiments

After installation, run the four `rank/csz × axonx/qlib` training, prediction and backtest combinations locally in the workspace containing a successful ETL:

```bash
python -m axonx_qlib_a158.scripts.compare_parameters \
  --workspace-path /path/to/workspace --etl-task '<etl_task_id>' \
  --labels rank csz --train-start 20150101 --train-end 20230101 \
  --pred-start 20230101 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

The script reuses one ETL locally for both parameter presets under each selected label and saves validation metrics, period summaries, input digests and Task IDs to `qlib_a158_comparison/` in the workspace. Backtesting ends on the actual prediction end date. Use `--help` for dates, TopN and fees. Omitting `--labels` compares the two parameter presets with the default rank label.

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
| Backtest `transaction_cost_rate`                  | `0.002`                 | Shared fee rate when the corresponding side override is unset   |
| Backtest `buy_cost_rate`                          | `None`                  | Buy rate; unset uses shared rate                                |
| Backtest `sell_cost_rate`                         | `None`                  | Sell rate; unset uses shared rate                               |
| Backtest `annualization_days`                     | `252`                   | Trading days used for annualization                             |

Consult `get_task_definition` in the execution environment for the complete parameter Schema.

## Features, labels, and backtest protocol

Original features use the `f_alpha158_*` namespace: 13 current-day price features and 29 rolling feature families over 5, 10, 20, 30, and 60 trading-day windows. Prices are adjusted, and trading-calendar and listing-status information are preserved.

ETL schema version 2 publishes independent `dataset`, `labels`, `market`, and `calendar` artifacts. Raw labels use the next market date; suspended or missing quotes invalidate the label without searching for a future resumption. Training filters exclusive cutoffs and handles tails before computing `label_return_rank` or `label_return_csz`; fitting, validation and final training transform their own eligible reference rows. Rank uses average ranks scaled to `[0,1]`; CSZ uses clipped daily returns and population standard deviation (`ddof=0`). Early stopping selects rounds using validation L2. Prediction does not require future labels; its statistics describe scores and signal-time eligibility. Studio renders the configured TopN sizes and marks incomplete market-data results as provisional.

Backtesting inherits AxonX `BaseStockBacktestTask`, reads independent prices and trading states, and marks positions to market daily. Blocked exits retain capital; unfilled targets are not replaced by lower-ranked stocks. `transaction_cost_rate` is the shared rate; `buy_cost_rate` / `sell_cost_rate` override each side independently, with unset sides using the shared rate. Pass `--buy-cost-rate 0.0005 --sell-cost-rate 0.0015` for qlib rates (0.05% buy / 0.15% sell); the normalized-cash ledger omits the RMB 5 minimum. Fees apply to executed notional; `top_ns` is an integer list. An optional `market_status_file` supplies confirmed suspensions (signal keys plus `market_status=suspended`); absent quotes are not inferred as suspension and affected runs report `incomplete_market_data`. Top30 contains signal targets; `positions`, `orders`, and `trades` record actual portfolio state.

For return, cost, IC, and holding definitions, see [Interpreting backtests](https://flowllm-ai.github.io/AxonX/en/research/backtest).

Required prediction columns, optional columns and metadata constraints are listed in the [prediction input contract](../../docs/en/reference/research-artifacts.md#prediction-inputs-for-stock-backtesting).

## Local validation

From the repository root, after installing development dependencies:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_qlib_a158.py tests/unit/test_alpha158_labels.py tests/unit/test_alpha158_backtest.py \
  tests/unit/test_stock_backtest.py tests/unit/test_stock_pipeline.py -q
```

These checks cover feature boundaries, label timing, four-way parameter comparisons, side fees, delayed exits and cash/position accounting.

<a id="experiments"></a>

## Final experiment settings and results

This section records this plugin’s final experiment. See the [three-version comparison](../../docs/en/research/experiments.md#comparison) for cross-plugin results. Metrics come from successful machine-45 Tasks and their metadata, summary.parquet, daily.parquet and trades.parquet; original artifacts remain in the execution workspace.

### Version configuration

158 Alpha158 features; feature_fraction=0.9; fixed holding_days=1.

Data, training windows, filtering, execution, and fee settings are maintained in the [three-version comparison](../../docs/en/research/experiments.md#comparison).

The model uses 158 features and refits the full training period after early stopping selects 422 rounds. Validation RankIC is 0.10789.

This experiment uses fixed expiry with `holding_days=1`.

### Metric definitions

Shared definitions for IC/RankIC, net returns, Sharpe, turnover, and active metrics are maintained in the [experiment comparison](../../docs/en/research/experiments.md#comparison). Portfolio metrics use 909 dates; active metrics use 908 benchmark-valid dates.

### Overall signals and full Top20 results

| Metric                                   | Alpha158 |
| ---------------------------------------- | -------: |
| Overall IC                               |   0.0530 |
| Overall RankIC                           |   0.0923 |
| Overall RankICIR (annualized)            |  12.8817 |
| Net annualized                           |    7.69% |
| Net cumulative return                    |   30.63% |
| Net Sharpe                               |   0.3624 |
| Net annualized volatility                |   28.20% |
| Max drawdown                             |  -38.64% |
| Daily return win rate                    |   53.47% |
| Mean daily two-sided turnover            |  198.83% |
| Mean daily cost / prior equity           |  0.1988% |
| Closed trades                            |   18,032 |
| Net active annualized vs universe mean   |   -3.47% |
| Net IR vs universe mean                  |  -0.1404 |
| Net active max drawdown vs universe mean |  -28.47% |
| Net active annualized vs HS300 proxy     |    2.77% |
| Net IR vs HS300 proxy                    |   0.2353 |
| Net active max drawdown vs HS300 proxy   |  -31.94% |

### Top30 results

| Scheme   | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| -------- | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Alpha158 |          0.99% |     0.1315 |      -40.59% |  199.03% |          -0.5933 |       -0.0776 |

### Top20 yearly results

| Year | Days | Alpha158 |
| ---- | ---: | -------: |
| 2023 |  242 |   -9.16% |
| 2024 |  242 |    5.09% |
| 2025 |  243 |   48.64% |
| 2026 |  182 |   -9.30% |

Yearly values are interval net annualized returns; 2026 ends October 8. Results report `incomplete_market_data`: missing quotes may delay exits and carry stale marks. Same-close fills are a proxy.

### Reproduce the experiment

Save Task/Run IDs and wait for success before each downstream submission; use the same `--target` for remote commands. Parameters below match the Setting table; verify remaining defaults with `get_task_definition` before submission.

```bash
axonx submit --task qlib_a158_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_a158_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 0.9 \
  --random-seed 42 --num-threads 8
axonx submit --task qlib_a158_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008
axonx submit --task qlib_a158_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<market_path>' --calendar-file '<calendar_path>' --labels-file '<labels_path>'
```

### Task provenance and input checks

Execution workspace: `/nas/jinli.yl/data/axon` on machine 45.

| Stage / scheme     | Task ID                                      | Run ID                             |
| ------------------ | -------------------------------------------- | ---------------------------------- |
| baseline: train    | `train#qlib_a158_train#2026100912mMlp`       | `710de1c0530b430e94e0b92e7634cd2a` |
| baseline: predict  | `predict#qlib_a158_predict#2026100912Qanw`   | `c8b97e5ec7bb483da455d988ec6216d3` |
| Alpha158: backtest | `backtest#qlib_a158_backtest#2026100916Y0Xb` | `d10c8a78be104ee7a8a492b9cc438bde` |

| Input    | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `3337bb98e59986b3d3e10730ecff49fae0d3d31b7d6b8e163fe19a63510a8aad` |

Core/plugin versions: 0.1.1 / 0.2.0; Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0. New data do not guarantee reproduction of the unpublished historical snapshot; raw artifacts are not committed.
