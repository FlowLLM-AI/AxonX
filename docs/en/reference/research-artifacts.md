---
title: Research artifacts and Studio presentation contracts
description: Production and consumption contracts for standard research outputs, file digests, training curves, and backtest tables.
---

# Research artifacts and Studio presentation contracts

Research Tasks publish results through typed `output_params`. Studio extracts presentation fields from successful tasks' `metadata.json`, then reads artifacts through file previews. This page distinguishes three layers of requirements: required Python base-class fields, fields actually read by Studio, and extension contracts of specific plugins.

![Artifact reading chain](../../figures/research/results-reading.svg)

## Mapping metadata to artifacts

Standard Task records store identity, input parameters, output parameters, and related information at the metadata top level. Research fields belong in `output_params`; placing them at the top level does not make Studio recognize them automatically.

The following is a structural excerpt, rather than complete TaskMetadata:

```json
{
  "output_params": {
    "artifacts": {
      "dataset": {
        "path": "alpha158.parquet",
        "size": 1024,
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
      }
    }
  }
}
```

The example size and digest only illustrate fields; calculate actual values from generated files. `artifact_record(path, task_dir)` generates a relative path, byte size, and SHA-256. `artifact_path(task_dir, metadata, name)` resolves a record and rejects absolute paths or paths escaping the task directory.

`BaseOutputParams.artifacts` defaults to an empty dictionary with type `dict[str, dict[str, Any]]`. The Python base class therefore does not fully validate each artifact's three fields. Producers should explicitly call the helpers to ensure pages and downstream consumers can read them.

Resolving paths through downstream helpers does not itself automatically verify every digest. qlib_a158 prediction separately verifies the model digest; this does not establish complete verification of all upstream data.

## Five base output types

Required below means the model has no default; not every field is displayed separately in Studio.

| Type     | Required base-class fields                                | Optional or default base-class fields                                     |
| -------- | --------------------------------------------------------- | ------------------------------------------------------------------------- |
| ETL      | `output_file`, `rows`, `date_range`                       | `feature_columns=[]`, `label_columns=[]`                                  |
| Analysis | `result_file`, `rows`                                     | `scores={}`                                                               |
| Train    | `model_files`, `train_rows`                               | `model_name`, feature/target columns, metrics, parameters, training_curve |
| Predict  | `predictions_file`, `score_columns`, `rows`, `date_range` | `output_columns=[]`, `protocol={}`, `statistics={}`                       |
| Backtest | `dimensions`, `protocol`, `date_range`, `days`            | Shared `artifacts={}`                                                     |

All types extend `BaseOutputParams`; output subclasses must declare extra fields or `extra=forbid` validation fails. `date_range` is a string mapping; pages read `start` and `end`, so producers should use these keys.

## ETL artifacts

The base class stores output-file descriptions and column names. qlib_a158 adds feature_count, symbols, schema, protocol, market_state, and related information, producing:

| Artifact name | File               | Purpose                                                   |
| ------------- | ------------------ | --------------------------------------------------------- |
| `dataset`     | `alpha158.parquet` | Source data for training, factor analysis, and prediction |
| `statistics`  | `alpha158.csv`     | Quality statistics for each feature column                |
| `labels`      | `labels.parquet`   | Fixed-next-market-day raw returns and availability        |
| `market`      | `market.parquet`   | Quotes, adjustment factors, execution flags and states    |
| `calendar`    | `calendar.parquet` | Market dates independent of prediction eligibility        |

qlib_a158 downstream consumers resolve data through `artifacts.dataset.path`; filling only `output_file` while omitting the mapping is insufficient. Output file fields store full path strings, while standard artifacts should use paths relative to the Task directory.

## Factor-analysis scores

`scores` has the shape “group name → metric name → value”:

```json
{
  "scores": {
    "quality": { "mean_abs_ic": 0.03, "positive_ratio": 0.6 },
    "coverage": { "valid_days": 120.0 }
  }
}
```

This illustrates a valid shape rather than a fixed qlib_a158 metric set. Studio dynamically iterates groups and metrics. Plugins should ensure metric names and definitions are understandable and explain samples, units, and calculation scope in detailed files or extended definition fields.

qlib_a158 actually generates `factor_analysis.csv` and `factor_quantiles.csv`, mapped as `result` and `quantiles`, respectively, and stores extension fields such as definitions and labels.

Training outputs use a nonempty `model_files` mapping from member ID to model path. Prediction outputs use a nonempty `score_columns` mapping from member ID to raw score column in `predictions_file`. Single-member producers use the same collection contract. Multi-model stock plugins select or aggregate raw scores before invoking the shared backtest ledger; `pred` is the final selection score.

This collection contract replaces the legacy `model_file` field and requires `score_columns` for predictions; legacy plugin outputs and historical metadata are not supported. Member count distinguishes single-member from multi-member output, not the number of prediction targets. A single model may have multiple targets, and multiple models may share one target.

## Training curve model

`TrainingCurve` is an explicitly validated model:

```json
{
  "x": ["1", "2", "3"],
  "y_left": {
    "train_l2": [0.09, 0.07, 0.06],
    "validation_l2": [0.1, 0.08, 0.085]
  },
  "y_right": {
    "validation_l1": [0.22, 0.2, 0.205]
  }
}
```

Requirements:

- x contains ordered string labels; all series align by position.
- Every series has exactly the same length as x, and every numeric value is finite.
- Nonempty x requires at least one left-axis series; the right axis cannot exist alone.
- Series names cannot repeat across the left and right axes.
- Empty x and empty groups on both axes indicate no curve data.

Series within the left-axis group should use similar units and numeric ranges; the right axis is only for a second scale group. The protocol does not support a third numeric axis. Studio performs only lightweight normalization when reading: charts filter out series with mismatched lengths and ignore nonfinite values when calculating axis ranges. They do not fully revalidate the Python model's rules or repair training history. Producers must validate with the model before publishing.

qlib_a158 places L2 on the left axis and L1 on the right; the curve is the tuning model's training/validation history. `model`, `feature_importance`, and `evaluation_history` reference the final model, feature importance, and history CSV, respectively.

## Prediction statistics

The base-class `statistics` field is an extensible mapping. Studio currently reads:

```text
statistics.days / symbols
statistics.pred.mean / min / median / max
statistics.buyable_rows / candidate_rows
statistics.indices.<column>.constituents / days_with_weights / null_rows
```

Missing fields appear as empty values on the page; this does not mean every prediction plugin must provide qlib_a158's stock statistics. qlib_a158 uses the artifact name `predictions` and file `predictions.parquet`.

Stock backtesting uses the shared `axonx.task.builtins.stock` contract. Prediction rows contain `trade_date`, `trade_time`, `ts_code`, `pred`, `is_model_candidate`, `is_buyable_at_signal`, `signal_price`, and `signal_adjustment_factor`; eligibility flags are non-null Boolean values. qlib_a158 also publishes `name`, `rank`, `buyable_rank`, and index weights. Predictions contain no future labels. ETL publishes independent `dataset`, `labels`, `market`, and `calendar` artifacts; `labels` stores `label_target_date`, `label_return`, `label_valid`, and `label_status` alongside the signal keys. Rank/CSZ targets are computed only during training after cutoff and sample filtering.

## Prediction inputs for stock backtesting

`BaseStockBacktestTask` reads these 8 required columns from prediction Parquet files. Both Alpha158 plugins publish this contract in `predictions.parquet`.

| Required column            | Type and constraints                                            | Meaning                                                              |
| -------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------- |
| `trade_date`               | Non-null string, valid YYYYMMDD, present in the market calendar | Signal date                                                          |
| `trade_time`               | Non-null string, valid HHMM; one signal time per backtest       | Signal time, for example `1500`                                      |
| `ts_code`                  | Non-null string                                                 | Stock identifier                                                     |
| `pred`                     | Non-null finite numeric value                                   | Ranking score; higher ranks first; not a return or probability       |
| `is_model_candidate`       | Non-null Boolean                                                | Model candidate eligibility                                          |
| `is_buyable_at_signal`     | Non-null Boolean                                                | Signal-time buyability filter                                        |
| `signal_price`             | Non-null finite numeric value                                   | Signal reference quote, stored separately from its adjustment factor |
| `signal_adjustment_factor` | Non-null finite numeric value                                   | Adjustment factor for the signal reference quote                     |

The prediction table must be nonempty, and the composite key `(trade_date, trade_time, ts_code)` must be unique and non-null. Stock identifiers and signal times must use the same conventions as the market table. Reference prices and adjustment factors should be positive according to their price meaning. Both eligibility flags must be `true` to enter the selection candidate pool, followed by the `index_codes` restriction.

These columns are optional for the base backtest:

| Optional column        | Use                                                                                                                                                                                                    |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `name`                 | Display name in details; defaults to `ts_code` when omitted                                                                                                                                            |
| `rank`, `buyable_rank` | Prediction-side helper ranks; backtesting computes target ranks from `pred` descending and `ts_code` ascending                                                                                         |
| `index_weight_<code>`  | Decimal index weights; `index_codes=["hs300"]` requires `index_weight_hs300`, with positive weights indicating membership in that candidate index; weight columns also supply benchmark return proxies |

Predictions need no feature columns, `actual_return`, future labels or future execution dates. `signal_price` and `signal_adjustment_factor` are signal reference information; execution and daily valuation use `price`, `adjustment_factor` and trading states from the independent `market` table.

Backtesting also requires independent `market` and `calendar` artifacts. Optional `labels` supplies IC, RankIC, NDCG, target label returns and benchmark returns; the portfolio ledger can run without labels. For explicit files, pass `input_file`, `market_file`, `calendar_file` and optional `labels_file`, where `input_file` is prediction Parquet.

When resolving a Predict Task ID, prediction metadata must publish an artifact record (relative `path`, `size`, `sha256`) under `output_params.artifacts.predictions` and declare `output_params.protocol.version=2`. `protocol.market_source_task` identifies the ETL Task supplying market, calendar and labels; an ETL source can also be supplied explicitly in `source_tasks`, or the corresponding file paths can be provided. Task resolution verifies source artifact digests. `statistics` is presentation information, not a selection input.

## Backtest dimensions and protocol

```json
{
  "dimensions": {
    "top_ns": [1, 5, 10, 30],
    "holding_detail_top_n": 30,
    "benchmarks": [{ "key": "universe", "label": "Universe" }]
  },
  "protocol": { "version": 2, "return_unit": "decimal" },
  "date_range": { "start": "20230103", "end": "20231229" },
  "days": 250
}
```

This illustrates a valid base-class structure. The shared stock Task publishes execution, valuation, allocation, fee, cutoff, and input-digest definitions in `protocol`, and `evaluation_status` identifies incomplete market data. The page is not a backtest engine that automatically validates protocol text; plugin authors must clearly state actual execution behavior and units.

Studio loads two tables from `artifacts.daily.path` and `artifacts.summary.path`, requesting 5000 rows per page and continuing according to `has_more` until the complete tables are read. Satisfying the Backtest output model alone does not guarantee usable charts.

## Presentation fields in the daily table

| Field                                    | Current Studio use                                                         |
| ---------------------------------------- | -------------------------------------------------------------------------- |
| `trade_date`                             | Date axis and date alignment between two strategies; uses YYYYMMDD strings |
| `candidate_count`                        | Candidate count                                                            |
| `ic`, `rank_ic`                          | Signal curves and moving averages                                          |
| `topN_net_return`, `topN_gross_return`   | Net compounded and gross additive curves                                   |
| `topN_turnover`, `topN_transaction_cost` | Turnover and cost inspection                                               |
| `topN_ndcg`                              | Ranking diagnostics for each configured Top N                              |
| `benchmark_<key>_return`                 | Benchmark return curves declared in dimensions                             |
| `top30_holdings`                         | Currently fixed Top 30 details                                             |

Details are arrays of structures; the frontend reads `rank`, `ts_code`, `name`, `prediction`, `daily_return`, and `weight`. `daily_return` is the fixed-next-market-day label and is null when unavailable at the cutoff. Actual entry/exit dates and delayed exits belong to the `positions` and `trades` artifacts; fills and unfilled reasons belong to `orders`.

The current page hardcodes `top30_holdings`; changing holding_detail_top_n does not automatically select another column. In qlib_a158, this field represents signal targets and includes candidates that did not trade; it must not be described as an actual holdings ledger.

## Presentation fields in the summary table

Each row uses `period_type` to identify `overall`, `year`, `quarter`, or `month`, and supplies `period`, `period_start`, `period_end`, and `trading_days`.

Signal fields include `ic_mean`, `icir`, and `rank_ic_mean`. Each Top N has:

```text
topN_net_cumulative_return
topN_net_annualized_return
topN_net_annualized_volatility
topN_net_max_drawdown
topN_net_win_rate
topN_average_turnover
topN_gross_cumulative_return
topN_gross_sharpe
topN_information_ratio_<benchmark key>
```

Replace N with the actual numbers in dimensions. The summary table is plugin output; return charts and strategy comparisons are calculated in the browser. qlib_a158 compounds gross cumulative summary returns, while its gross return chart is additive. See [Backtest interpretation](../research/backtest.md) for calculation conventions.

## Producer acceptance checks

1. Validate output_params with the actual output subclass.
2. Write files first, then call artifact_record and publish metadata.
3. Resolve every standard artifact from the Task directory using artifact_path.
4. Check dates, numeric units, boolean columns, and arrays of structures against current Studio fields.
5. Validate curves and downstream contracts, retaining explicit execution descriptions in protocol.

Do not manually substitute placeholder digests for real files or alter metadata to conceal a failed execution. All charts depend on shared contracts between their producers and readers.

## Implementation references

- [`Base research models`](../../../axonx/task/contracts/)
- [`Artifact helpers`](../../../axonx/task/storage/artifacts.py)
- [`Studio reading mappings`](../../../axonx_studio/src/features/research/ResearchPage.tsx)
- [`Backtest presentation types`](../../../axonx_studio/src/features/research/backtest/types.ts)
- [`qlib_a158 output implementations`](../../../plugins/qlib_a158/axonx_qlib_a158/)
