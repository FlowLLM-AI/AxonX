# Alpha158 plugin

[English](README.md) · [简体中文](README_ZH.md) · [Plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management)

An independent AxonX research plugin for data processing, factor analysis, LightGBM training, out-of-sample prediction, and TopN backtesting.

Uses 158 price and volume features as a research baseline. For context features and ablation experiments, see [Alpha158 Enhanced](../a158_enhanced/README.md).

![Research tasks and artifacts](../../docs/figures/research/workflow.svg)

## Install and inspect

Requires Python 3.12+; local Task execution supports macOS and Linux. Install into the execution service’s Python environment, then restart the service to reload contributions. LightGBM, NumPy, and Polars are installed as dependencies.

```bash
pip install axonx-alpha158
axonx plugin list
axonx plugin show axonx-alpha158
```

For source development, run from the repository root:

```bash
pip install -e ./plugins/a158
axonx plugin inspect ./plugins/a158
```

The local CLI environment may differ from the remote service environment. For remote deployment, configure the target service token and specify the target explicitly:

```bash
export AXONX_TARGET_TOKEN='<service token>'
axonx plugin install ./plugins/a158 --target 'http://<host>:1024'
axonx plugin list --target 'http://<host>:1024'
```

Restart the target service as indicated by `restart_required`, then query Task definitions. See [plugin management](https://flowllm-ai.github.io/AxonX/en/plugins/management).

## Prepare data

Configure `AXONX_TUSHARE_TOKEN` in the execution service environment and use the built-in `download_tushare_task` to prepare Tushare Parquet data. The default ETL input is `tushare/` inside the workspace, rather than the current shell directory.

```bash
axonx submit --task download_tushare_task \
  --start-date 20140101 --end-date 20260930 \
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

Prepare sufficient preceding history for rolling windows. The example trains from 2015, so downloads start in 2014. The default download only looks back seven calendar days and does not provide a full history. For credentials, partition layout, and updates, see [Tushare downloads](https://flowllm-ai.github.io/AxonX/en/research/tushare).

## Tasks and execution

| Task            | Upstream              | Outputs                                                             |
| --------------- | --------------------- | ------------------------------------------------------------------- |
| `a158_etl`      | Workspace market data | Features, labels, trading status, and statistics                    |
| `a158_factor`   | ETL Task ID           | Factor diagnostics and analysis                                     |
| `a158_train`    | ETL Task ID           | Model, training protocol, validation curves, and feature importance |
| `a158_predict`  | Train Task ID         | Full-cross-section predictions and statistics                       |
| `a158_backtest` | Predict Task ID       | Daily backtests, period summaries, and holding-related artifacts    |

Factor analysis branches from ETL and is not a prerequisite for training. Submit in the following order, use the actual returned Task IDs, and wait for each stage to succeed before submitting its downstream stage.

```bash
axonx submit --task a158_etl --start-date 20150101 --end-date 20260930

# After ETL succeeds
axonx submit --task a158_factor --source-tasks '<etl_task_id>'
axonx submit --task a158_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101

# After training succeeds
axonx submit --task a158_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20260930

# After prediction succeeds
axonx submit --task a158_backtest --source-tasks '<predict_task_id>'
```

For every wait, provide both identifiers from that submission:

```bash
axonx --client-timeout 86400 wait_task \
  --task-id '<task_id>' --run-id '<run_id>'
axonx get_task_definition --task a158_train
```

For remote execution, add the same `--target` to all submission, wait, and definition queries. Install and execute against the same service environment.

![Studio task lineage](../../docs/figures/studio/task-lineage.png)

## Key parameters

| Stage / parameter                                 | Default                 | Meaning                                                         |
| ------------------------------------------------- | ----------------------- | --------------------------------------------------------------- |
| ETL `start_date` / `end_date`                     | `20140101` / null       | First / last output dates, inclusive                            |
| ETL `min_history_coverage`                        | `0.8`                   | Minimum history coverage for rolling features                   |
| Train `train_start` / `train_end`                 | `20150101` / `20230101` | Inclusive start, exclusive cutoff                               |
| Train `label_column`                              | `label_1d_rank`         | Daily cross-sectional return rank target                        |
| Train `trim_tail`                                 | `0.025`                 | Remove 2.5% of raw returns from each daily tail                 |
| Train `validation_ratio`                          | `0.10`                  | Last training dates reserved for internal validation            |
| Train `num_boost_round` / `early_stopping_rounds` | `1000` / `50`           | Maximum rounds / early stopping patience                        |
| Train `random_seed`                               | `42`                    | Model sampling seed                                             |
| Predict `pred_start` / `pred_end`                 | `20230101` / null       | Prediction interval; start must not precede the training cutoff |
| Backtest `transaction_cost_rate`                  | `0.002`                 | Transaction cost multiplied by actual daily turnover            |
| Backtest `annualization_days`                     | `252`                   | Trading days used for annualization                             |

Consult `get_task_definition` in the execution environment for the complete parameter Schema.

## Features, labels, and backtest protocol

Original features use the `f_alpha158_*` namespace: 13 current-day price features and 29 rolling feature families over 5, 10, 20, 30, and 60 trading-day windows. Prices are adjusted, and trading-calendar and listing-status information are preserved.

The normal label is adjusted close-to-close return from signal day T to T+1. If the planned exit is unavailable, exit is delayed until the first sellable date. Training, factor evaluation, and signal ranking metrics use valid, undelayed one-day samples. Prediction retains the full cross section without filtering stocks by future labels.

Backtesting ranks same-day signals and simulates buying at the same-day close using daily tradability proxies. It does not model after-close queuing or partial fills. Positions retain capital until actual exit; open positions remain at cost, and net returns are booked on realized exits. Top30 holding details describe signal targets, rather than the live position book.

For return, cost, IC, and holding definitions, see [Interpreting backtests](https://flowllm-ai.github.io/AxonX/en/research/backtest).

## Inspect results in Studio

Inspect parameters, logs, metadata, and upstream relationships in Task details. Research result pages display ETL, factor, training, prediction, and backtest artifacts. The screenshots below illustrate existing experiments and do not represent every run of this plugin.

![Training curves](../../docs/figures/studio/training-curves.png)

![Out-of-sample predictions](../../docs/figures/studio/prediction-results.png)

![Overall backtest metrics](../../docs/figures/studio/backtest-overall.png)

## Troubleshooting and source

| Problem                      | Check                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------ |
| Missing registered Task      | Installation environment, entry point, service restart, and target machine     |
| ETL missing data             | Workspace Tushare partitions, three static files, and historical date coverage |
| Prediction date error        | pred_start must not precede train_end; model and ETL metadata must be complete |
| Results differ from examples | Data snapshot, feature groups, dates, labels, parameters, and costs            |

[Task registration](axonx_alpha158/plugin.yaml) · [ETL](axonx_alpha158/etl.py) · [Factor analysis](axonx_alpha158/analysis.py) · [Training](axonx_alpha158/train.py) · [Prediction](axonx_alpha158/predict.py) · [Backtesting](axonx_alpha158/backtest.py)

[Research workflow](https://flowllm-ai.github.io/AxonX/en/research/workflow) · [Research results](https://flowllm-ai.github.io/AxonX/en/research/results) · [Task management](https://flowllm-ai.github.io/AxonX/en/guides/task-management)

The repository’s [run_pipeline.sh](axonx_alpha158/scripts/run_pipeline.sh) demonstrates handle extraction, stage-by-stage waits, and failure exits. It refreshes only the last seven days of market data; prepare full historical data before using it.

## Local validation

From the repository root, after installing development dependencies:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_alpha158_labels.py tests/unit/test_alpha158_backtest.py -q
```

These checks cover label timing, delayed exits, costs, and position accounting.
