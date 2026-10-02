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

Resolving paths through downstream helpers does not itself automatically verify every digest. a158 prediction separately verifies the model digest; this does not establish complete verification of all upstream data.

## Five base output types

Required below means the model has no default; not every field is displayed separately in Studio.

| Type | Required base-class fields | Optional or default base-class fields |
| --- | --- | --- |
| ETL | `output_file`, `rows`, `date_range` | `feature_columns=[]`, `label_columns=[]` |
| Analysis | `result_file`, `rows` | `scores={}` |
| Train | `model_file`, `train_rows` | `model_name`, feature/target columns, metrics, parameters, training_curve |
| Predict | `predictions_file`, `rows`, `date_range` | `output_columns=[]`, `protocol={}`, `statistics={}` |
| Backtest | `dimensions`, `protocol`, `date_range`, `days` | Shared `artifacts={}` |

All types extend `BaseOutputParams`; output subclasses must declare extra fields or `extra=forbid` validation fails. `date_range` is a string mapping; pages read `start` and `end`, so producers should use these keys.

## ETL artifacts

The base class stores output-file descriptions and column names. a158 adds feature_count, symbols, schema, labels, market_state, and related information, producing:

| Artifact name | File | Purpose |
| --- | --- | --- |
| `dataset` | `alpha158.parquet` | Source data for training, factor analysis, and prediction |
| `statistics` | `alpha158.csv` | Quality statistics for each column |

a158 downstream consumers resolve data through `artifacts.dataset.path`; filling only `output_file` while omitting the mapping is insufficient. Historical fields may store full path strings, while standard artifacts should use paths relative to the Task directory.

## Factor-analysis scores

`scores` has the shape “group name → metric name → value”:

```json
{
  "scores": {
    "quality": {"mean_abs_ic": 0.03, "positive_ratio": 0.6},
    "coverage": {"valid_days": 120.0}
  }
}
```

This illustrates a valid shape rather than a fixed a158 metric set. Studio dynamically iterates groups and metrics. Plugins should ensure metric names and definitions are understandable and explain samples, units, and calculation scope in detailed files or extended definition fields.

a158 actually generates `factor_analysis.csv` and `factor_quantiles.csv`, mapped as `result` and `quantiles`, respectively, and stores extension fields such as definitions and labels.

## Training curve model

`TrainingCurve` is an explicitly validated model:

```json
{
  "x": ["1", "2", "3"],
  "y_left": {
    "train_l2": [0.09, 0.07, 0.06],
    "validation_l2": [0.10, 0.08, 0.085]
  },
  "y_right": {
    "validation_l1": [0.22, 0.20, 0.205]
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

a158 places L2 on the left axis and L1 on the right; the curve is the tuning model's training/validation history. `model`, `feature_importance`, and `evaluation_history` reference the final model, feature importance, and history CSV, respectively.

## Prediction statistics

The base-class `statistics` field is an extensible mapping. Studio currently reads:

```text
statistics.days / symbols
statistics.pred.mean / min / median / max
statistics.buyable_rows / valid_return_rows / candidate_rows
statistics.indices.<column>.constituents / days_with_weights / null_rows
```

Missing fields appear as empty values on the page; this does not mean every prediction plugin must provide a158's stock statistics. a158 uses the artifact name `predictions` and file `predictions.parquet`.

Columns required for backtesting belong to the plugin contract and are not automatically guaranteed by the Predict base class. a158 requires trade_date, ts_code, name, pred, actual_return, label_valid, is_buyable, entry_is_buyable, exit_is_sellable, entry_date, exit_date, and exit_delayed, and checks that the relevant status columns are Boolean.

## Backtest dimensions and protocol

```json
{
  "dimensions": {
    "top_ns": [1, 5, 10, 30],
    "holding_detail_top_n": 30,
    "benchmarks": [{"key": "universe", "label": "Universe"}]
  },
  "protocol": {"actual_return_unit": "decimal"},
  "date_range": {"start": "20230103", "end": "20231229"},
  "days": 250
}
```

This illustrates a valid base-class structure. a158 provides more detailed protocol text for candidate_filter, execution, portfolio, turnover, net_return, and related topics. The page is not a backtest engine that automatically validates protocol text; plugin authors must clearly state actual execution behavior and units.

Studio loads two tables from `artifacts.daily.path` and `artifacts.summary.path`, requesting 5000 rows per page and continuing according to `has_more` until the complete tables are read. Satisfying the Backtest output model alone does not guarantee usable charts.

## Presentation fields in the daily table

| Field | Current Studio use |
| --- | --- |
| `trade_date` | Date axis and date alignment between two strategies; uses YYYYMMDD strings |
| `candidate_count` | Candidate count |
| `ic`, `rank_ic` | Signal curves and moving averages |
| `topN_net_return`, `topN_gross_return` | Net compounded and gross additive curves |
| `topN_turnover`, `topN_transaction_cost` | Turnover and cost inspection |
| `topN_ndcg` | Ranking diagnostics at the fixed display size |
| `benchmark_<key>_return` | Benchmark return curves declared in dimensions |
| `top30_holdings` | Currently fixed Top 30 details |

Details are arrays of structures; the frontend reads `rank`, `ts_code`, `name`, `prediction`, `daily_return`, and `weight`. a158 also stores entry_date, exit_date, and exit_delayed for protocol analysis.

The current page hardcodes `top30_holdings`; changing holding_detail_top_n does not automatically select another column. In a158, this field represents signal targets and includes candidates that did not trade; it must not be described as an actual holdings ledger.

## Presentation fields in the summary table

Each row uses `period_type` to identify `overall`, `year`, `quarter`, or `month`, and supplies `period`, `period_start`, `period_end`, and `trading_days`.

Signal fields are `ic_mean`, `icir`, `rank_ic_mean`, and `rank_icir`. Each Top N has:

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

Replace N with the actual numbers in dimensions. The summary table is plugin output; return charts and strategy comparisons are calculated in the browser. a158 compounds gross cumulative summary returns, while its gross return chart is additive. See [Backtest interpretation](../research/backtest.md) for calculation conventions.

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
- [`a158 output implementations`](../../../plugins/a158/axonx_alpha158/)
