# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` builds cross-sectional context research on `qlib_a158`. It retains 158 base features and adds 26 features in four groups: market, liquidity, relative performance and interactions. ETL publishes 184 features; `context_groups` selects model inputs.

Training defaults to `label_return_rank` and `parameter_preset=axonx`, inheriting cutoff-safe labels, early stopping on the last 10% of dates and full-period refitting. Predictions and fixed-expiry backtests reuse the base plugin; `qlib_strategy` supplies portfolio policies.

## Factors and timing

| Group       | Features |
| ----------- | -------: |
| market      |       11 |
| liquidity   |        6 |
| relative    |        5 |
| interaction |        4 |

Definitions are in [cross_section.py](axonx_qlib_factor/internal/cross_section.py). Amount groups use history through T−1; same-day context becomes available after close. Returns use adjacent market-date adjusted quotes, preserving gaps. Computation uses market data and current states only. ETL records groups, timing, coverage and daily diagnostics.

`context_groups` accepts comma-separated groups; `none` selects only base features. Default groups: `liquidity` (164 model features), selected using training-period validation RankIC.

## Install and run

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx get_task_definition --task qlib_factor_train --target http://research.example:1024

axonx submit --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx --target http://research.example:1024
axonx submit --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Save each returned Task ID and Run ID and wait for `succeeded` before submitting downstream work. `qlib_factor_analysis` is an optional diagnostic branch. With the core from this checkout, Task-only wheel updates through the remote installation Job apply without restarting; restart when `restart_required` is true and verify Task definitions. Direct pip/source changes and older cores without plugin import refresh require restart; the core must support side-specific fees. See [Qlib Alpha158](../qlib_a158/README.md) for source data, labels and execution assumptions.

## Experiments and reproduction

![Signal quality](../../docs/figures/benchmark/qlib-signal-quality.svg)

The [experiment plan](DEVELOPMENT_PLAN_EN.md) defines 15 nonempty group combinations and a no-context control. Train on `[20150101,20230101)`, predict from `20230101`, and charge 0.05% buy / 0.15% sell fees. Training-period validation RankIC selects the context group; all candidates are reported over the shared OOS interval.

[Results](EXPERIMENT_RESULTS.md) · [Execution checks](EXPERIMENT_PROCESS_EN.md) · [Metric index](experiments/README.md) · [Three-layer comparison](../qlib_a158/THREE_LAYER_EXPERIMENTS.md).
