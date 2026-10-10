---
title: Quantitative Research Workflow
description: Connect data, factor analysis, training, prediction, and backtesting with the Alpha158 plugin.
---

# Quantitative Research Workflow

AxonX provides research task execution, records, artifacts, and Studio visualization. This page uses `plugins/qlib_a158/` in the repository as a concrete algorithm implementation, building a complete path from Tushare data to backtest results. The enhanced `qlib_factor` plugin uses separate `qlib_factor_*` registration names and adds training feature-group parameters. Both share research stages and basic artifact structures, but cross-plugin upstream reuse still requires checking Task definitions, feature order, and protocols. See the [enhanced plugin](../../../plugins/qlib_factor/README.md) for usage.

![From data to research evidence](../../figures/research/workflow.svg)

## Before you start

- Complete the [quickstart](../getting-started/quickstart.md), with a working service token and connection.
- Install the qlib_a158 plugin in the service environment executing tasks. Installing it in the local CLI environment does not automatically change a remote machine's environment.
- Have Tushare history covering the training and prediction periods, plus necessary master data, in the workspace.
- Keep research tasks and upstream artifacts in the same workspace, or prepare complete upstream directories using [task synchronization](../guides/task-sync.md).

```bash
pip install axonx-qlib-a158
```

Direct pip installation requires a service restart. Remote `axonx plugin install` refreshes Task definitions; restart only when `restart_required=true`. Query the task catalog with `axonx list_installed_task_definitions`. Expect `qlib_a158_etl`, `qlib_a158_factor`, `qlib_a158_train`, `qlib_a158_predict`, and `qlib_a158_backtest`.

## What each research stage produces

| Stage           | Registered name         | Input source                   | Main results                                   |
| --------------- | ----------------------- | ------------------------------ | ---------------------------------------------- |
| Download        | `download_tushare_task` | Tushare API                    | Raw partitions in workspace `tushare/`         |
| ETL             | `qlib_a158_etl`         | Raw partitions and master data | `alpha158.parquet`, statistics CSV             |
| Factor analysis | `qlib_a158_factor`      | One ETL Task                   | Factor diagnostics and quantile return CSV     |
| Training        | `qlib_a158_train`       | One ETL Task                   | LightGBM model, importance, validation history |
| Prediction      | `qlib_a158_predict`     | One Train Task                 | Full cross-sectional prediction Parquet        |
| Backtest        | `qlib_a158_backtest`    | One Predict Task               | Daily and summary Parquet                      |

Factor analysis is an independent downstream stage of ETL; training does not depend on its success. Prediction resolves the ETL upstream through training metadata, so retain both the training directory and ETL data.

## Submitting and waiting for a stage

Replace Task IDs in the following commands with actual values returned by the previous stage. Registered names cannot replace Task IDs.

```bash
axonx submit --task qlib_a158_etl --start-date 20150101
```

The returned `answer` is a TaskHandle. Save its `task_id` and `run_id`. Accepted submission only means a worker was created; then wait for that execution:

```bash
axonx --client-timeout 86400 wait_task \
  --task-id '<returned task_id>' --run-id '<returned run_id>'
```

Pass it downstream only after confirming final success. See [task management](../guides/task-management.md) for full submission and query methods. A client timeout does not mean the background task was cancelled.

## From ETL to out-of-sample prediction

```bash
# After ETL succeeds, factor analysis can run independently
axonx submit --task qlib_a158_factor --source-tasks '<ETL Task ID>'

# The training end date is excluded from the training interval
axonx submit --task qlib_a158_train --source-tasks '<ETL Task ID>' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank

# After training succeeds, prediction must start no earlier than train_end
axonx submit --task qlib_a158_predict --source-tasks '<Train Task ID>' \
  --pred-start 20230101 --pred-end 20231231

# After prediction succeeds, generate backtest artifacts
axonx submit --task qlib_a158_backtest --source-tasks '<Predict Task ID>' \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

Perform the wait from the previous section between each submission. `source_tasks` uses ASCII commas to separate Task IDs. Each qlib_a158 stage requires a single upstream task of the corresponding type; do not arbitrarily add tasks of that type.

Training reserves the final dates in trading-day order for validation, with a default validation ratio of 10%. Validation and early stopping first select the iteration count, then all valid samples in the training window fit the final model. Saved training curves come from tuning; they are not the final model's performance on an independent test set.

## Data scope and label boundaries

By default, ETL outputs available data from `20140101`, while rolling features read earlier history. Downloading the latest 7 calendar days cannot support multi-year training or complete rolling windows.

qlib_a158 publishes independent feature, raw-label, market, and calendar artifacts. Labels use the next market date at the same time; suspension or missing data invalidates that fixed-day return without extending its horizon. Training excludes label target dates at or beyond the exclusive cutoff and computes rank/CSZ targets after sample filtering. Prediction retains the full cross-section without joining labels. Backtesting selects signal-day candidates and values actual positions each market day; blocked exits retain capital.

The default training target `label_return_rank` is a cross-sectional rank label. Prediction `pred` is a model score and cannot be interpreted directly as a return or probability of a price rise.

## Viewing results in Studio

See [interpreting results](results.md) for actual UI examples by stage. ETL, factor, training, and prediction views show dates, metrics, and artifacts. Screenshots come from existing remote-workspace experiments; this page's dates need not produce the same values.

Open ETL, factor, training, prediction, and backtest pages in order and select the corresponding tasks. Research lists read `metadata.json` from successful tasks. Use the task page for status and logs of running tasks.

The recommended reading order is ETL dates, rows, and feature columns; training validation details; prediction coverage; then backtest protocols, costs, and returns. See [strategy comparison](strategy-comparison.md) for comparisons between strategies.

## From executing a chain to designing an experiment

A completed execution provides parameters and artifacts. Evaluating improvements also requires controls, ablations, screening, and independent confirmation. Plan comparisons with [experiment design and confirmation](experiments.md), then inspect common windows with [strategy comparison](strategy-comparison.md). See [Qlib Factor](../../../plugins/qlib_factor/README.md) for the agent-developed feature case and reproduction guide.

## Using the repository script

[`run_pipeline.sh`](../../../plugins/qlib_a158/axonx_qlib_a158/scripts/run_pipeline.sh) implements submission, handle reading, stage-by-stage waiting, and failure exits. Use it as a reference for connecting commands:

```bash
bash plugins/qlib_a158/axonx_qlib_a158/scripts/run_pipeline.sh
```

The script installs the plugin, refreshes the latest 7 days of raw data, and uses existing historical partitions for multi-year research. It does not automatically download all missing history. Prepare data before running it and check whether its fixed dates suit your research interval.

## Common failures and actions

| Symptom                                   | First checks                                                    |
| ----------------------------------------- | --------------------------------------------------------------- |
| Registered name does not exist            | Plugin environment and restart status of the execution service  |
| Missing daily, adj_factor, or master data | `tushare/` partitions and static files                          |
| No valid labels in the training interval  | ETL dates, trading status, exit labels, and training boundaries |
| Prediction starts before training ends    | `pred_start` and metadata `train_end_exclusive`                 |
| Model validation fails                    | Whether the model file in the training directory was replaced   |
| Backtest fields are missing               | Whether prediction artifacts match the qlib_a158 protocol       |

Lineage graphs record explicit upstream relationships. They do not automatically schedule, fill in, or rerun the research chain. Rerunning with a fixed `task_name` replaces the directory record of a finished task; use different names and retain artifacts when comparing experiments.

## Related documentation and implementation

- [Tushare data](tushare.md), [Interpreting results](results.md), [Interpreting backtests](backtest.md)
- [Research artifact protocol](../reference/research-artifacts.md)
- [qlib_a158 plugin manifest](../../../plugins/qlib_a158/axonx_qlib_a158/plugin.yaml)
- [Training implementation](../../../plugins/qlib_a158/axonx_qlib_a158/train.py), [Prediction implementation](../../../plugins/qlib_a158/axonx_qlib_a158/predict.py)
