import type { TaskDefinition, TaskStatus } from "../features/tasks/types";
import type { WorkspacePreview } from "../features/workspace/types";
import type { DailyRow, SummaryRow } from "../features/research/backtest/types";
import { strategyStats } from "../features/research/compare/model";

export const epoch = "2026-01-05T09:00:00.000Z";
export const kinds = [
  "etl",
  "analysis",
  "train",
  "predict",
  "backtest",
] as const;
export const definitions: TaskDefinition[] = kinds.map((kind) => ({
  name: `playground.${kind}`,
  source: "plugin",
  plugin: "playground",
  task_type: kind,
  description:
    "Browser simulation / 浏览器模拟：parameters select a synthetic result; no research algorithm is executed.",
  input_schema: {
    type: "object",
    properties: {
      task_name: { type: "string", default: `Demo ${kind}` },
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

export function taskStatus(kind: string, id: string, name: string): TaskStatus {
  return {
    task_id: id,
    run_id: id,
    task_type: kind,
    task_name: name,
    config: { task_name: name },
    state: "succeeded",
    pid: null,
    created_at: epoch,
    started_at: epoch,
    finished_at: epoch,
    steps: ["Prepare", "Simulate", "Write artifacts"].map((name) => ({
      name,
      started_at: epoch,
      finished_at: epoch,
      percentage: 100,
    })),
    result: { output_dir: `runs/${id}` },
    error: "",
    exit_code: 0,
    log_path: `runs/${id}/task.log`,
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
    content,
    data,
    size: content.length,
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
  task: TaskStatus,
  strategy = "steady",
  source: string[] = [],
) {
  const path = `runs/${task.task_id}`;
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
      ? "model.json"
      : task.task_type === "analysis"
        ? "scores.json"
        : "samples.parquet";
  const artifactFiles =
    task.task_type === "backtest"
      ? { daily: "daily.parquet", summary: "summary.parquet" }
      : { output };
  const outputKey = {
    etl: "output_file",
    analysis: "result_file",
    train: "model_file",
    predict: "predictions_file",
  }[task.task_type];
  if (task.task_type === "backtest") {
    files.set(`${path}/daily.parquet`, table(daily));
    files.set(`${path}/summary.parquet`, table(periods));
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
      { path: file, size: files.get(`${path}/${file}`)!.size, sha256: "" },
    ]),
  );
  files.set(
    `${path}/metadata.json`,
    json({
      task_id: task.task_id,
      task_type: task.task_type,
      reg_name: `playground.${task.task_type}`,
      created_at: task.created_at,
      input_params: {
        ...task.config,
        task_name: task.task_name,
        source_tasks: source.join(","),
      },
      output_params: {
        ...(outputKey ? { [outputKey]: `${path}/${output}` } : {}),
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
        protocol: { version: 2 },
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
    }),
  );
  files.set(`${path}/task.log`, {
    kind: "text",
    content: "Synthetic research completed. No Python or LLM was executed.\n",
    size: 75,
    truncated: false,
  });
}

export function seed() {
  const tasks = new Map<string, TaskStatus>();
  const files = new Map<string, WorkspacePreview>();
  let source: string[] = [];
  for (const kind of [...kinds, "backtest"] as const) {
    const variant = tasks.has(`${kind}#demo`) ? "volatile" : "steady";
    const id = `${kind}#${variant === "steady" ? "demo" : "volatile"}`;
    const task = taskStatus(kind, id, `Demo ${kind} / ${variant}`);
    if (kind === "backtest") source = ["predict#demo"];
    task.config.source_tasks = source.join(",");
    tasks.set(id, task);
    addArtifacts(files, task, variant, source);
    if (variant === "steady") source = [id];
  }
  seedOnline(tasks, files);
  files.set(
    "tushare/daily/sample.parquet",
    table(
      dailyRows("steady").flatMap((row) =>
        (row.top30_holdings || []).map((holding) => ({
          trade_date: row.trade_date,
          ts_code: holding.ts_code,
          close: 10 + holding.rank / 10,
          daily_return: holding.daily_return,
        })),
      ),
    ),
  );
  files.set("tushare/README.md", {
    kind: "markdown",
    content:
      "# Synthetic market data / 合成行情\n\nAll securities, returns and results are fictional. / 所有证券、收益和结果均为虚构。",
    size: 150,
    truncated: false,
    frontmatter: null,
    frontmatter_error: null,
  });
  const failed = taskStatus("train", "train#failed", "Demo failure");
  failed.state = "failed";
  failed.error = "Simulated missing input";
  failed.exit_code = 1;
  failed.result = {};
  tasks.set(failed.task_id, failed);
  return { tasks, files };
}

function seedOnline(
  tasks: Map<string, TaskStatus>,
  files: Map<string, WorkspacePreview>,
) {
  const windows = [
    {
      key: "1445",
      status: "done",
      rows: 4850,
      coverage: 0.998,
      elapsed_seconds: 12.4,
      metrics: { candidate_count: 4820 },
    },
    {
      key: "1450",
      status: "incomplete",
      rows: 4600,
      coverage: 0.947,
      elapsed_seconds: 60,
      reason: "deadline_exceeded",
    },
    {
      key: "1500",
      status: "skipped",
      reason: "window_missed",
      rows: 0,
      elapsed_seconds: 0,
    },
  ];
  const samples = [
    { kind: "api", name: "Synthetic realtime collection", result: { windows } },
    {
      kind: "inference",
      name: "Synthetic single-model inference",
      result: {
        model_identity: {
          path: "synthetic/model.pt",
          fingerprint: "demo-sha256-001",
          protocol: "synthetic-16bar-v1",
        },
        windows: [
          windows[0],
          {
            key: "1450",
            status: "incomplete",
            rows: 0,
            reason: "inputs_timeout",
            elapsed_seconds: 60,
          },
        ],
      },
    },
    {
      kind: "analysis",
      name: "Synthetic prediction reconciliation",
      result: {
        comparisons: [
          {
            key: "1445 / same snapshot",
            status: "consistent",
            metrics: {
              top5_overlap: "5 / 5",
              top10_overlap: "10 / 10",
              max_score_delta: 0,
              candidate_difference: 0,
            },
          },
          {
            key: "1445 / revised source",
            status: "different",
            reason: "source_revision",
            metrics: {
              top5_overlap: "4 / 5",
              top10_overlap: "8 / 10",
              max_score_delta: 0.0012,
              candidate_difference: 3,
            },
          },
          {
            key: "1450",
            status: "protocol_mismatch",
            reason: "model_mismatch",
          },
          { key: "1500", status: "missing", reason: "inputs_timeout" },
        ],
      },
    },
  ];
  for (const sample of samples) {
    const id = `${sample.kind}#playground_online#demo`;
    const task = taskStatus(sample.kind, id, sample.name);
    task.config.task_name = sample.name;
    if (sample.kind === "analysis")
      task.config.comparison_keys = sample.result.comparisons?.map(
        (item) => item.key,
      );
    task.config.source_tasks =
      sample.kind === "analysis"
        ? "inference#playground_online#demo"
        : sample.kind === "inference"
          ? "api#playground_online#demo"
          : "";
    const reportName =
      sample.kind === "analysis" ? "comparison.json" : "manifest.json";
    task.result = {
      ...sample.result,
      [sample.kind === "analysis" ? "report_file" : "manifest_file"]:
        `runs/${id}/${reportName}`,
      artifacts: {
        report: {
          path: reportName,
          size: JSON.stringify(sample.result).length,
          sha256: "",
        },
      },
    };
    tasks.set(id, task);
    files.set(`runs/${id}/${reportName}`, json(sample.result));
    files.set(
      `runs/${id}/metadata.json`,
      json({
        task_id: id,
        task_type: sample.kind,
        reg_name: "playground_online",
        created_at: epoch,
        input_params: task.config,
        output_params: task.result,
      }),
    );
  }
}
