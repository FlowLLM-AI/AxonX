---
title: Research artifacts and Studio presentation contracts
description: Production and consumption contracts for standard research outputs, file revisions, training curves, and backtest tables.
---

# Research artifacts and Studio presentation contracts

Research file records use `revision="<size>:<mtime_ns>"`, not content checksums. Publication, upstream input access and online history check file size and modification time rather than hashing payload bytes. Copies preserve nanosecond mtime; published files must be immutable and replaced atomically. Metadata checks cannot detect edits preserving both size and mtime. Model identity fingerprints member revisions; configuration and source-code fingerprints remain SHA-256.

Research Tasks publish results through typed `output_params`. Studio extracts presentation fields from successful tasks' `metadata.json`, then reads artifacts through file previews. This page distinguishes three layers of requirements: required Python base-class fields, fields actually read by Studio, and extension contracts of specific plugins.

Data tables use `<name>.parquet`; CSV is reserved for statistical reports and every CSV filename ends in `_stats.csv`. Examples are `features.parquet` with `features_stats.csv`, and `alpha158.parquet` with `alpha158_stats.csv`. Realtime windows and row-level prediction differences remain Parquet. Execution records, native model files, Markdown reports and hierarchical JSON reports keep their own formats.

## Shared protocol v1

AxonX owns the shared research protocol in `axonx.task.models.artifacts`. Research protocol headers require `version=1` and a `TaskType` value in `task_type`. Readers reject missing headers and other versions.

One training plan has one Task ID for all seeds and rolling windows. Its `metadata.json.output_params` is a `BaseTrainOutputParams`: shared contracts live in `feature_protocol` and `training_target`; `model_groups` stores ordered groups with shared training/use ranges; each group's `models` map stores member configurations, state, row counts, parameters, metrics, curves and timing. Each member references an `artifacts` entry by `model_artifact`; final files are flat under `models/`. Prediction selects by `[use_from,use_to)`; the last group has `use_to=null` and serves later dates.

Each offline prediction Task publishes one `predictions.parquet`, including all dates, seeds and score columns. Stock rows are unique by `(trade_date, trade_time, ts_code)`. `metadata.json.output_params.protocol` contains `score_columns` and ordered, non-overlapping `windows`. Each window records `[prediction_start,prediction_end_exclusive)`, a `models` mapping from score member to training model name, and that group's `model_identity`. Readers select the window by prediction date. Model configurations remain in training metadata; producing executions and consumed revisions remain in `input_sources`. The prediction file's path, size and revision appear only in `output_params.artifacts.predictions`; actual dates are in the parquet, with lightweight `rows`, `date_range`, `output_columns` and optional `statistics` summaries in output metadata. Prediction outputs always belong to the Task directory. Rolling parents retain their own `predictions.parquet` snapshot so reusable child Tasks cannot overwrite a published parent result.

Online prediction uses the same `PredictionProtocol` score mapping with type `inference`, stored in the published commit within Task metadata. Its model identity, date, time and artifact records belong to the commit, without an extra model window or protocol file. The Qlib plugin uses `models_sha256` and `features_sha256` identity entries; the shared window type allows plugin-defined string keys and values. Qlib feature contracts and fingerprints come from `axonx_qlib_a158.internal.modeling`; fingerprints include semantic rules and ordered features, excluding locations, date coverage and quality counters. Package release versions are independent.

The Qlib feature contract uses one ordered `feature_columns` list. Models record the selected subset and order in metadata. Signal eligibility is `is_buyable_at_signal`; executable market conditions remain `can_buy` and `can_sell`. Training reports validation scores through `metrics` and row counts before/after trimming and for tuning/validation.

## Mapping metadata to artifacts

Standard Task records store identity, input parameters, output parameters, and related information at the metadata top level. Research fields belong in `output_params`; placing them at the top level does not make Studio recognize them automatically.

Task inputs use `input_sources` for producer execution and artifact revisions. An explicit external prediction file has no producing Task reference; Portfolio records its revision once in `protocol.input_revisions`.

The following is a structural excerpt, rather than complete TaskMetadata:

```json
{
  "output_params": {
    "artifacts": {
      "dataset": {
        "path": "alpha158.parquet",
        "size": 1024,
        "revision": "1024:1700000000000000000"
      }
    }
  }
}
```

The example size and revision only illustrate fields; calculate actual values from generated files. `artifact_record(path, task_dir)` generates a relative path, byte size, and revision. `verify_artifact(task_dir, ArtifactRecord.model_validate(record))` resolves a record and checks that a regular file matches its recorded size and revision. Paths escaping the Task directory or traversing symlinks are rejected.

`BaseOutputParams.artifacts` is `dict[str, ArtifactRecord]`. Every output validates each relative path, nonnegative byte size and file revision. `task.artifact_path(name)` resolves a published output without a separate absolute-path field.

`task.artifact_path(name)` resolves an output path. `upstream_artifact()` and `upstream_artifacts()` require successful non-replica producers and read their published files directly. Task metadata records the producing execution and file revisions in `input_sources`; execution rejects replaced sources or changed files before reporting success. Revisions use size and nanosecond mtime, not content hashes. Business compatibility remains the plugin's responsibility.

## Research stage outputs

Required below means the model has no default; not every field is displayed separately in Studio.

| Type      | Required base-class fields         | Optional or default base-class fields           |
| --------- | ---------------------------------- | ----------------------------------------------- |
| ETL       | `rows`, `date_range`               | `feature_columns=[]`, `label_columns=[]`        |
| Analysis  | `rows`                             | `scores={}`                                     |
| Train     | `feature_protocol`, `model_groups` | `training_target={}`, `artifacts={}`            |
| Predict   | `protocol`, `rows`, `date_range`   | `output_columns=[]`, `statistics={}`            |
| Portfolio | `portfolios`, `protocol`           | Readable identities and frozen signal artifacts |
| Backtest  | `portfolios`, `protocol`           | Shared `artifacts={}`                           |

Consumers read the model index directly from Task metadata.

All types extend `BaseOutputParams`; output subclasses must declare extra fields or `extra=forbid` validation fails. `date_range` is a string mapping; pages read `start` and `end`, so producers should use these keys.

Training declares an ordered `output_params.model_groups` list. Each group owns `train_start`, `train_end_exclusive`, `use_from` and optional exclusive `use_to`; its `models` map contains member configurations, state, artifacts and curves. Groups must be ordered and non-overlapping; selection requires completed members and complete coverage of the requested dates. Prediction score mappings are declared only in `protocol.score_columns`, and prediction data is registered as `artifacts.predictions`. Single-member producers use the same collection contract. Stock plugins select or aggregate raw scores before invoking the shared backtest ledger; `pred` is the final selection score.

Member count distinguishes single-member from multi-member output, independently of prediction target count.

## ETL artifacts

Axon/Axon2 A-stock ETL stores feature semantics, provenance and quality information in `metadata.json.output_params.protocol`. Each Task owns one signal time (`protocol.trade_time`), uses stable artifact roles, and publishes fixed feature filenames `features.parquet` and optional `features_stats.csv`. When an external output directory is selected, copies under the Task's `artifacts/` retain the original filenames.

The base class stores output-file descriptions and column names. qlib_a158 adds feature_count, symbols, schema, protocol, market_state, and related information, producing:

| Artifact name | File                 | Purpose                                                   |
| ------------- | -------------------- | --------------------------------------------------------- |
| `dataset`     | `alpha158.parquet`   | Source data for training, factor analysis, and prediction |
| `statistics`  | `alpha158_stats.csv` | Quality statistics for each feature column                |
| `labels`      | `labels.parquet`     | Fixed-next-market-day raw returns and availability        |
| `market`      | `market.parquet`     | Quotes, adjustment factors, execution flags and states    |
| `calendar`    | `calendar.parquet`   | Market dates independent of prediction eligibility        |

All consumers resolve output files through the task-relative `artifacts` registry. ETL, analysis, prediction and training register task-relative output paths.

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

qlib_a158 actually generates `factor_analysis_stats.csv` and `factor_quantiles_stats.csv`, mapped as `result` and `quantiles`, respectively, and stores extension fields such as definitions and labels.

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

Series within the left-axis group should use similar units and numeric ranges; the right axis is only for a second scale group. The protocol does not support a third numeric axis. Studio reads the validated training curve directly from `output_params.model_groups[group_index].models[model_name].training_curve`; chart rendering filters mismatched series and nonfinite values.

qlib_a158 places L2 on the left axis and L1 on the right; the curve is the tuning model's training/validation history stored directly in model metadata. `model` and `feature_importance` reference the final model and `feature_importance_stats.csv`.

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

Predict publishes the complete score cross section. `BaseStockPortfolioTask` constructs portfolios using signal-time information. `BaseStockBacktestTask` consumes Portfolio artifacts and independently resolves market data, calendar and optional labels. Construction never consults future returns.

Portfolio reads original scores and signal context in place from Predict. It publishes one `rankings.parquet` with `universe_key`, `trade_date`, `trade_time`, `ts_code`, and `target_rank` for every eligible candidate in every universe. `score_column` references an unchanged upstream column; actual score aggregation publishes only the keys and final `pred` in one `scores.parquet`. `universes` maps ranking keys to universe definitions. Different Top N values and strategies share these files. Candidate flags are reconstructed from ranking membership; targets use `target_rank <= top_n` with weight `1/top_n`, leaving unfilled slots in cash.

```bash
axonx exec --task qlib_a158_portfolio --upstream-task-ids '["<Predict Task ID>"]' --top-ns '[5,10,30]' --holding-days 1
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<Portfolio Task ID>"]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

`strategies` optionally declares multiple strategy definitions. Construction expands universe × strategy × Top N; omitting it uses the Task default. `output_params.portfolios` stores readable identities and references to the shared rankings and optional scores. No per-portfolio signal or target table is written.

## Backtest dimensions and protocol

Portfolio outputs are lists. Each entry carries a readable `portfolio_id` dictionary. Producers may add fields; shared meanings use `universe`, `score_selection`, `strategy`, `top_n`, `allocation`, and `trade_time`. Key order does not affect identity and duplicate identities are rejected. Locate a portfolio across Tasks using its producer Task ID and readable identity.

```json
{
  "signals_format": "stock-signals-v3",
  "portfolios": [
    {
      "portfolio_id": {
        "universe": {
          "kind": "all"
        },
        "score_selection": {
          "method": "model"
        },
        "strategy": {
          "kind": "fixed_expiry",
          "holding_days": 1
        },
        "top_n": 5,
        "allocation": "equal_slot",
        "trade_time": "1500"
      },
      "artifacts": {
        "rankings": "rankings"
      }
    }
  ],
  "protocol": {
    "version": 1,
    "task_type": "portfolio",
    "market_upstream_task_id": "etl#qlib_a158_etl#data"
  },
  "artifacts": {
    "rankings": {
      "path": "rankings.parquet",
      "size": 100,
      "revision": "100:1"
    }
  },
  "score_column": "pred",
  "universes": [
    {
      "key": "all",
      "label": "All market",
      "parameters": {
        "kind": "all"
      }
    }
  ]
}
```

Backtest `upstream_task_ids` requires a Portfolio Task and may also specify an ETL. `portfolio_ids` optionally selects identities. Costs, missing-market assumptions, cutoff, annualization and benchmark coverage belong to Backtest. Reports retain the `portfolios` list, adding `dimensions`, `date_range`, `days`, `evaluation_status`, and references to `daily`, `summary`, `orders`, `positions`, and `trades`. Files live under `portfolios/<ordinal>/`; ordinals only identify storage locations.

Plugin Portfolio Tasks override `build_universes()`, `select_universe()`, `prepare_signals()`, and `strategy()`. Evaluation extensions use Backtest `evaluation_files()` and `evaluate()` so offline and online callers share policy resources and accounting. Targets express intent. Cash, holdings and market restrictions determine actual fills; stateful policies consult actual positions in the ledger.

## Unified backtest signals

Portfolio and online reports declare `stock-signals-v3`. `PortfolioReader` reconstructs complete signals from the referenced predictions, final scores and frozen rankings. Reads validate the producer execution and artifact revisions recorded in `input_sources`; a replaced prediction publication is rejected. Backtest reads labels directly from ETL and publishes only accounting and evaluation results. Online commits keep their own predictions, rankings and optional scores; continuous signals are reconstructed from daily commits without a cumulative signals copy. Studio and comparison readers use the same separation.

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

## Windowed work and online history

Backtest plugins override `evaluation_files(params)` for policy resources and `evaluate(signals, market, calendar, labels, identity, params, *, as_of_date, files)` for shared evaluation. The ordinary Backtest Task and online/comparison callers use this same method; `identity` supplies the published strategy and Top N. Callers capture the declared file revisions before evaluation.

`BaseWindowTask` runs ordered `ExecutionWindow` inputs with timezone-aware start/end times. It publishes each `WindowResult` as `done`, `skipped`, `incomplete` or `failed`. These are business outcomes, separate from the Task lifecycle state. `BaseRealtimeApiTask` polls `collect()`; `BaseInferenceTask` fixes a nonempty model identity for the entire execution. Bound network calls and retries by `DeadlineBudget.remaining_seconds`.

`publish_online()` writes a completed inference result under the Task's ordinary `outputs/<HHMM>/` directory and returns an `OnlineCommit` containing the producing execution, model identity, protocol and registered files. The executor's `persistent/task.lock` owns execution; `persistent/history.jsonl` appends one terminal metadata JSON object after each run. Online business files use ordinary Task output directories.

Axon2 daily parents use `outputs/<HHMM>/<model>/`. Online parents retain predictions, rankings, optional scores, compact market data and display ledgers; feature matrices, calendars, weights and debug data remain in inference children. Evidence references pin child execution times and artifact revisions. Report `portfolios` maps stable portfolio keys to complete identities. Ledger tables use a `portfolio_key` column: positions record the current-day state, orders/trades record current-day events, daily contains one row per portfolio and day, and summary records as-of statistics. Studio assembles history from daily snapshots, independently of mutable children. Comparison parents retain metadata diagnostics, top_comparisons.json and optional bounded differences.parquet samples. Replaced inference evidence is unavailable for recomputation and never replaced with a newer execution.

Mean/rank-mean ensemble keys omit rolling seed membership while daily identities retain the actual members. Explicit seed selections keep distinct keys.

## Producer acceptance checks

1. Validate output_params with the actual output subclass.
2. Write files first, then call artifact_record and publish metadata.
3. Resolve and verify every registered artifact with `verify_artifact`; pin upstream files before consuming them.
4. Check dates, numeric units, boolean columns, and arrays of structures against current Studio fields.
5. Validate curves and downstream contracts, retaining explicit execution descriptions in protocol.

Do not manually substitute placeholder digests for real files or alter metadata to conceal a failed execution. All charts depend on shared contracts between their producers and readers.

## Studio wire contracts

Studio keeps the task record and its nested `output_params`, without a flattened research copy. Research and comparison pages share a filtered task-index query; filtering precedes deep copying. Online report settings live only in `report.commit.protocol.report`. Agent history responses expose display blocks; original transcripts stay in the session store. Run `npm run contracts:generate` and `npm run contracts:check` in `axonx_studio/` after changing Python wire contracts.

## Implementation references

- [`Base research models`](../../../axonx/task/models/)
- [`Artifact helpers`](../../../axonx/task/storage/artifacts.py)
- [`Studio reading mappings`](../../../axonx_studio/src/features/research/ResearchPage.tsx)
- [`Backtest presentation types`](../../../axonx_studio/src/features/research/backtest/types.ts)
- [`qlib_a158 output implementations`](../../../plugins/qlib_a158/axonx_qlib_a158/)
