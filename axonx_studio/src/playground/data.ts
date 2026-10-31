import { taskDirectory } from "../shared/lib/tasks";
import type { DailyRow, SummaryRow } from "../features/research/backtest/types";
import { strategyStats } from "../features/research/compare/model";
import type { TaskDefinition } from "../features/tasks/model";
import type { TaskMetadata } from "../shared/api/contracts";
import type { WorkspacePreview } from "../shared/api/workspace";

export const epoch = "2026-01-05T09:00:00.000Z";

export const kinds = [
  "etl",
  "analysis",
  "train",
  "predict",
  "portfolio",
  "backtest",
] as const;
export const definitions: TaskDefinition[] = kinds.map((kind) => ({
  name: `playground_${kind}`,
  source: "plugin",
  plugin: "playground",
  task_type: kind,
  description:
    "Browser simulation / 浏览器模拟：parameters select a synthetic result; no research algorithm is executed.",
  input_schema: {
    type: "object",
    properties: {
      task_name: {
        anyOf: [{ type: "string" }, { type: "null" }],
        default: null,
        pattern: "^[A-Za-z0-9-]{1,32}$",
      },
      upstream_task_ids: {
        type: "array",
        items: { type: "string" },
        default: [],
      },
      strategy: {
        type: "string",
        enum: ["steady", "volatile"],
        default: "steady",
      },
      outcome: {
        type: "string",
        enum: ["success", "failure"],
        default: "success",
      },
    },
  },
  output_schema: {
    type: "object",
    properties: { output_dir: { type: "string" } },
  },
}));

export function taskStatus(
  kind: TaskMetadata["task_type"],
  id: string,
): TaskMetadata {
  return {
    parent_task_id: null,
    version: 1,
    report_kind: kind === "inference" ? "online" : null,
    task_id: id,
    task_type: kind,
    reg_name: id.split("#")[1],
    input_params: { task_name: id.split("#")[2], upstream_task_ids: [] },
    input_sources: {},
    state: "succeeded",
    pid: 1234,
    machine_id: "playground",
    execution_target: null,
    workspace_dir: null,
    process_started_at: "2026-01-01T00:00:00Z",
    created_at: epoch,
    started_at: epoch,
    finished_at: epoch,
    children: [],
    steps: ["Prepare", "Simulate", "Write artifacts"].map((name) => ({
      name,
      label: "",
      parent: null,
      group: "",
      state: "done",
      phase: "",
      completed: null,
      total: null,
      unit: "",
      scheduled_at: null,
      deadline: null,
      updated_at: epoch,
      metrics: {},
      files: {},
      error: "",
      started_at: epoch,
      finished_at: epoch,
      percentage: 100,
    })),
    output_params: { output_dir: taskDirectory(id) },
    error: "",
    exit_code: 0,
    log_path: "task.log",
    replica: null,
  };
}

const dates: string[] = [];
for (let day = 0; dates.length < 60; day++) {
  const date = new Date(Date.UTC(2026, 0, 5 + day));
  if (date.getUTCDay() !== 0 && date.getUTCDay() !== 6)
    dates.push(date.toISOString().slice(0, 10).replaceAll("-", ""));
}

export function dailyRows(strategy: string): DailyRow[] {
  return dates.map((trade_date, i) => {
    const daily =
      (strategy === "volatile" ? 0.011 : 0.005) * Math.sin(i * 0.73) + 0.0008;
    return {
      trade_date,
      candidate_count: 30,
      ic: 0.06 + Math.sin(i) * 0.03,
      rank_ic: 0.07 + Math.sin(i) * 0.02,
      benchmark_demo_return: 0.003 * Math.sin(i * 0.6) + 0.0002,
      ...Object.fromEntries(
        [5, 10, 15, 20, 30].flatMap((n) => [
          [`top${n}_gross_return`, daily + 0.0002],
          [`top${n}_net_return`, daily],
          [`top${n}_turnover`, 0.15],
          [`top${n}_ndcg`, 0.65 + Math.sin(i) * 0.05],
        ]),
      ),
      top30_holdings: Array.from({ length: 30 }, (_, rank) => ({
        rank: rank + 1,
        ts_code: `DEMO${String(rank + 1).padStart(3, "0")}`,
        name: `Synthetic ${rank + 1}`,
        prediction: 0.03 - rank * 0.001,
        daily_return: daily,
        weight: 1 / 30,
      })),
    };
  });
}

export function table(rows: Record<string, unknown>[]): WorkspacePreview {
  const columns = Object.keys(rows[0] || {});
  return {
    kind: "parquet",
    size: JSON.stringify(rows).length,
    columns,
    rows: rows.map((row) => columns.map((key) => row[key])),
    column_schema: columns.map((name) => ({
      name,
      type: typeof rows[0]?.[name],
      nullable: false,
    })),
    row_count: rows.length,
    row_group_count: 1,
    offset: 0,
    limit: rows.length,
    has_more: false,
  };
}
export function json(data: unknown): WorkspacePreview {
  const content = JSON.stringify(data, null, 2);
  return {
    kind: "json",
    content: "",
    data,
    size: new TextEncoder().encode(content).length,
    parse_error: null,
    truncated: false,
  };
}

function annualRatio(values: number[]) {
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const deviation = Math.sqrt(
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
      (values.length - 1),
  );
  return deviation ? (mean / deviation) * Math.sqrt(252) : 0;
}

export function addArtifacts(
  files: Map<string, WorkspacePreview>,
  task: TaskMetadata,
  strategy = "steady",
  upstreamIds: string[] = [],
) {
  const path = taskDirectory(task.task_id);
  const daily = dailyRows(strategy);
  const periods: SummaryRow[] = [];
  for (const type of ["overall", "year", "quarter", "month"] as const) {
    const groups = new Map<string, DailyRow[]>();
    for (const row of daily) {
      const key =
        type === "overall"
          ? "overall"
          : type === "year"
            ? row.trade_date.slice(0, 4)
            : type === "quarter"
              ? "2026Q1"
              : row.trade_date.slice(0, 6);
      groups.set(key, [...(groups.get(key) || []), row]);
    }
    for (const [period, rows] of groups) {
      const mean = (key: string) =>
        rows.reduce((sum, row) => sum + Number(row[key]), 0) / rows.length;
      periods.push({
        period_type: type,
        period,
        period_start: rows[0].trade_date,
        period_end: rows.at(-1)!.trade_date,
        trading_days: rows.length,
        ic_mean: mean("ic"),
        rank_ic_mean: mean("rank_ic"),
        icir: annualRatio(rows.map((row) => Number(row.ic))),
        rank_icir: annualRatio(rows.map((row) => Number(row.rank_ic))),
        ...Object.fromEntries(
          [5, 10, 15, 20, 30].flatMap((n) => {
            const stats = strategyStats(
              rows.map((row) => ({ date: row.trade_date, a: row, b: row })),
              "a",
              n,
            );
            return Object.entries({
              net_cumulative_return: stats.cumulative,
              net_annualized_return: stats.annualized,
              net_annualized_volatility: stats.volatility,
              net_max_drawdown: stats.maxDrawdown,
              net_win_rate: stats.winRate,
              average_turnover: stats.turnover,
              gross_sharpe: annualRatio(
                rows.map((row) => Number(row[`top${n}_gross_return`])),
              ),
              net_relative_max_drawdown_demo: strategyStats(
                rows.map((row) => ({
                  date: row.trade_date,
                  a: {
                    ...row,
                    [`top${n}_net_return`]:
                      Number(row[`top${n}_net_return`]) -
                      Number(row.benchmark_demo_return),
                  },
                  b: row,
                })),
                "a",
                n,
              ).maxDrawdown,
              information_ratio_demo: annualRatio(
                rows.map(
                  (row) =>
                    Number(row[`top${n}_gross_return`]) -
                    Number(row.benchmark_demo_return),
                ),
              ),
              net_return: stats.cumulative,
              gross_cumulative_return:
                rows.reduce(
                  (equity, row) =>
                    equity * (1 + Number(row[`top${n}_gross_return`])),
                  1,
                ) - 1,
              ndcg_mean: mean(`top${n}_ndcg`),
            }).map(([key, value]) => [`top${n}_${key}`, value]);
          }),
        ),
      });
    }
  }
  const predictions = daily.flatMap((row) =>
    (row.top30_holdings || []).map((holding) => ({
      trade_date: row.trade_date,
      ts_code: holding.ts_code,
      pred: holding.prediction,
      trade_time: "1500",
      name: holding.name,
      is_model_candidate: true,
      is_buyable_at_signal: true,
      signal_price: 10,
      signal_adjustment_factor: 1,
      rank: holding.rank,
      buyable_rank: holding.rank,
    })),
  );
  const output =
    task.task_type === "train"
      ? "models/synthetic_seed_0_fit_end_20230101_use_20230101-onward.json"
      : task.task_type === "analysis"
        ? "scores.json"
        : task.task_type === "predict"
          ? "predictions.parquet"
          : "samples.parquet";
  const artifactFiles =
    task.task_type === "backtest"
      ? {
          all_daily: "portfolios/0/daily.parquet",
          all_summary: "portfolios/0/summary.parquet",
          hs300_daily: "portfolios/1/daily.parquet",
          hs300_summary: "portfolios/1/summary.parquet",
        }
      : task.task_type === "train"
        ? {
            model:
              "models/synthetic_seed_0_fit_end_20230101_use_20230101-onward.json",
          }
        : {
            [(
              {
                etl: "dataset",
                predict: "predictions",
                portfolio: "targets",
                analysis: "result",
              } as Partial<Record<TaskMetadata["task_type"], string>>
            )[task.task_type] || "output"]: output,
          };
  if (task.task_type === "backtest") {
    for (const [index] of ["all", "hs300"].entries()) {
      files.set(`${path}/portfolios/${index}/daily.parquet`, table(daily));
      files.set(`${path}/portfolios/${index}/summary.parquet`, table(periods));
    }
  } else
    files.set(
      `${path}/${output}`,
      output.endsWith("json")
        ? json(
            task.task_type === "train"
              ? { kind: "synthetic-model", strategy }
              : { momentum: 0.08, value: 0.04, quality: -0.02 },
          )
        : table(predictions),
    );
  const artifacts = Object.fromEntries(
    Object.entries(artifactFiles).map(([key, file]) => [
      key,
      {
        path: file,
        size: files.get(`${path}/${file}`)!.size,
        revision: "1:1",
      },
    ]),
  );
  const metadata = {
    ...task,
    task_id: task.task_id,
    task_type: task.task_type,
    reg_name: task.reg_name,
    created_at: task.created_at,
    input_params: {
      ...task.input_params,
      task_name: task.input_params.task_name,
      upstream_task_ids: [...upstreamIds],
    },
    output_params: {
      rows: predictions.length,
      train_rows: 1200,
      days: 60,
      date_range: { start: dates[0], end: dates.at(-1) },
      feature_columns: ["momentum", "value", "quality"],
      label_columns: ["label_return", "label_valid"],
      target_columns: ["label_return_rank"],
      output_columns: Object.keys(predictions[0]),
      model_name: "Synthetic model",
      parameters: { strategy },
      metrics: { mse: 0.002, ic: 0.06 },
      scores: {
        "ic/return_1d": { momentum: 0.08, value: 0.04, quality: -0.02 },
      },
      training_curve: {
        x: Array.from({ length: 20 }, (_, i) => String(i + 1)),
        y_left: {
          train: Array.from({ length: 20 }, (_, i) => 0.04 / (i + 1)),
          validation: Array.from(
            { length: 20 },
            (_, i) => 0.045 / (i + 1) + 0.002,
          ),
        },
        y_right: {},
      },
      evaluation_status: "done",
      protocol: {
        version: 1,
        task_type: task.task_type,
        ...(task.task_type === "predict"
          ? {
              score_columns: { model: "pred" },
              windows: [
                {
                  prediction_start: dates[0],
                  prediction_end_exclusive: new Date(
                    Date.parse(
                      dates[dates.length - 1].replace(
                        /^(\d{4})(\d{2})(\d{2})$/,
                        "$1-$2-$3",
                      ),
                    ) + 86400000,
                  )
                    .toISOString()
                    .slice(0, 10)
                    .replaceAll("-", ""),
                  models: { model: "synthetic" },
                  model_identity: { model: "synthetic" },
                },
              ],
            }
          : {}),
      },
      statistics: {
        days: 60,
        symbols: 30,
        pred: { min: 0.001, max: 0.03, mean: 0.0155, median: 0.0155 },
        buyable_rows: 1800,
        candidate_rows: 1800,
        indices: {},
      },
      dimensions: {
        top_ns: [5, 10, 30],
        holding_detail_top_n: 30,
        benchmarks: [{ key: "demo", label: "Synthetic benchmark" }],
      },
      artifacts,
    },
  };
  if (task.task_type === "train") {
    Object.assign(metadata, {
      output_params: {
        feature_protocol: {
          version: 1,
          task_type: "etl",
          feature_family: "synthetic",
        },
        training_target: { label_column: "label_return_rank" },
        model_groups: [
          {
            train_start: "20150101",
            train_end_exclusive: "20230101",
            use_from: "20230101",
            use_to: null,
            models: {
              "synthetic_seed_0_fit_end_20230101_use_20230101-onward": {
                model_artifact: "model",
                state: "succeeded",
                model: {
                  model_type: "Synthetic model",
                  feature_names: ["momentum", "value", "quality"],
                  random_seed: 0,
                },
                train_rows: 1200,
                parameters: { strategy },
                metrics: metadata.output_params.metrics,
                training_curve: metadata.output_params.training_curve,
                started_at: task.started_at,
                finished_at: task.finished_at,
                elapsed_seconds: 1,
                error: "",
              },
            },
          },
        ],
        artifacts,
      },
    });
  }
  if (task.task_type === "backtest") {
    const { days, date_range, dimensions, evaluation_status, ...shared } =
      metadata.output_params;
    Object.assign(metadata, {
      output_params: {
        ...shared,
        signals_format: "stock-signals-v3",
        portfolios: ["all", "hs300"].flatMap((key) =>
          [5, 10, 30].map((n) => ({
            portfolio_id: {
              universe:
                key === "all"
                  ? { kind: "all" }
                  : { kind: "index", index_codes: ["hs300"] },
              strategy: { kind: "fixed_expiry", holding_days: 1 },
              top_n: n,
              allocation: "equal_slot",
              trade_time: "1500",
            },
            days,
            date_range,
            dimensions: { ...dimensions, top_ns: [n] },
            evaluation_status,
            artifacts: { daily: `${key}_daily`, summary: `${key}_summary` },
          })),
        ),
      },
    });
  }
  if (task.task_type === "portfolio") {
    const prepared = predictions.map((row) => ({
      universe_key: "all",
      trade_date: row.trade_date,
      trade_time: row.trade_time,
      ts_code: row.ts_code,
      target_rank: row.rank,
    }));
    files.set(`${path}/rankings.parquet`, table(prepared));
    const plans = [5, 10, 30].map((n) => {
      return {
        portfolio_id: {
          universe: { kind: "all" },
          score_selection: { method: "model" },
          strategy: { kind: "fixed_expiry", holding_days: 1 },
          top_n: n,
          allocation: "equal_slot",
          trade_time: "1500",
        },
        artifacts: { rankings: "rankings" },
      };
    });
    Object.assign(metadata, {
      output_params: {
        signals_format: "stock-signals-v3",
        score_column: "pred",
        universes: [
          { key: "all", label: "All market", parameters: { kind: "all" } },
        ],
        portfolios: plans,
        protocol: { version: 1, task_type: "portfolio" },
        artifacts: {
          rankings: {
            path: "rankings.parquet",
            size: files.get(`${path}/rankings.parquet`)!.size,
            revision: "1:1",
          },
        },
      },
    });
  }
  Object.assign(task, metadata);
  files.set(`${path}/metadata.json`, json(task));
  files.set(`${path}/task.log`, {
    kind: "text",
    content: "Synthetic research completed. No Python or LLM was executed.\n",
    size: 75,
    truncated: false,
  });
}
