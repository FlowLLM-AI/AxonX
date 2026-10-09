# Alpha158 Factor

[English](README.md) · [简体中文](README_ZH.md)

`a158_factor` inherits `a158`, retaining its 158 base features and adding the existing 26 factors (184 features). ETL, training, prediction, factor analysis and ordinary backtesting reuse the baseline lifecycle. Training defaults to market, liquidity and interaction groups, giving 179 model features. Select other groups through `context_groups`.

## Factors and timing

[ cross_section.py](axonx_alpha158_factor/internal/cross_section.py) defines market, liquidity, relative and interaction groups. Amount groups use history through T−1; same-day context is available after close. Adjacent-market-day adjusted returns remain missing when quotes are missing. Factors never consume future labels. ETL records groups, timing rules and daily context diagnostics.

## Installation and execution

```bash
axonx plugin install plugins/a158 --target http://research.example:1024
axonx plugin install plugins/a158_factor --target http://research.example:1024
axonx submit --task a158f_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx submit --task a158f_train --source-tasks '<etl_task_id>' --train-start 20150101 --train-end 20230101 --context-groups market,liquidity,interaction --target http://research.example:1024
axonx submit --task a158f_predict --source-tasks '<train_task_id>' --pred-start 20230101 --target http://research.example:1024
axonx submit --task a158f_backtest --source-tasks '<predict_task_id>' --top-ns '[5,10,20,30]' --as-of-date 20261008 --target http://research.example:1024
```

Use the returned Task ID and Run ID and wait for `succeeded` before submitting downstream, following the [development guide](../../docs/en/dev_guide.md). `a158f_factor` provides optional factor diagnostics. `context_groups` defaults to `market,liquidity,interaction`; choose a subset or `none`.

## Three-layer experiment

Train on 2015–2022; predict and backtest the complete interval from 20230101 to the common data cutoff. Report only Top5/10/20/30, charging 0.2% on every executed side. The [three-layer record](../a158/THREE_LAYER_EXPERIMENTS.md) stores tasks, settings, input digests and results. This layer uses ordinary backtesting; [a158_strategy](../a158_strategy/README.md) reuses its predictions and changes portfolio decisions only.

Earlier experiments used different windows and remain historical evidence: [previous results](EXPERIMENT_RESULTS.md) · [previous metrics](experiments/README.md). They are excluded from this three-layer comparison.

## Compatibility with the former enhanced plugin

This source replaces `plugins/a158_enhanced` with `plugins/a158_factor`. The distribution, Python package and plugin entry become `axonx-alpha158-factor`, `axonx_alpha158_factor` and `alpha158_factor`; new Task names use `a158f_` instead of `a158e_`. Training defaults to `market,liquidity,interaction`. Install the new package and restart the service before submitting new tasks. Existing task IDs, metadata and artifacts are not rewritten. To rerun old `a158e_` tasks, retain or reinstall the original enhanced-plugin version; the new factor plugin does not register those names. Historical reports below describe the original enhanced version.
