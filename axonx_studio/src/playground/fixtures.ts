import type { StudioPage } from "../shared/api/contracts";
import type { DailyRow, SummaryRow } from "../features/research/backtest/types";
import { strategyStats } from "../features/research/compare/model";
import type { TaskDefinition, TaskMetadata } from "../features/tasks/types";
import type { WorkspacePreview } from "../features/workspace/types";

export const epoch = "2026-01-05T09:00:00.000Z";
export const studioPages: StudioPage[] = [
  {
    id: "online",
    title: { en: "Online prediction", zh: "在线预测" },
    view: "pipeline",
    category: "online_prediction",
  },
  {
    id: "nightly",
    title: { en: "Evening comparison", zh: "晚间比对" },
    view: "pipeline",
    category: "comparison",
  },
  {
    id: "data",
    title: { en: "Data updates", zh: "数据更新" },
    view: "tasks",
    category: "data_update",
  },
];

export const kinds = [
  "etl",
  "analysis",
  "train",
  "predict",
  "backtest",
] as const;
export const definitions: TaskDefinition[] = kinds.map((kind) => ({
  category: null,
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

export function taskStatus(
  kind: TaskMetadata["task_type"],
  id: string,
  name: string,
): TaskMetadata {
  return {
    parent_run_id: null,
    version: 1,
    category: null,
    report_kind: kind === "inference" ? "online" : null,
    task_id: id,
    run_id: id,
    task_type: kind,
    reg_name: name,
    source: { kind: "exec" },
    input_params: { task_name: name },
    state: "succeeded",
    pid: 1234,
    machine_id: "playground",
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
    output_params: { output_dir: `${id.split("#")[0]}/${id}` },
    error: "",
    exit_code: 0,
    log_path: `${id.split("#")[0]}/${id}/task.log`,
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
  source: string[] = [],
) {
  const path = `${task.task_type}/${task.task_id}`;
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
      ? "model.json"
      : task.task_type === "analysis"
        ? "scores.json"
        : "samples.parquet";
  const artifactFiles =
    task.task_type === "backtest"
      ? {
          all_daily: "universes/all/daily.parquet",
          all_summary: "universes/all/summary.parquet",
          hs300_daily: "universes/hs300/daily.parquet",
          hs300_summary: "universes/hs300/summary.parquet",
        }
      : task.task_type === "train"
        ? { model: "model.json", model_manifest: "models.json" }
        : {
            [(
              {
                etl: "dataset",
                train: "model_manifest",
                predict: "predictions",
                analysis: "result",
              } as Partial<Record<TaskMetadata["task_type"], string>>
            )[task.task_type] || "output"]: output,
          };
  if (task.task_type === "backtest") {
    for (const universe of ["all", "hs300"]) {
      files.set(`${path}/universes/${universe}/daily.parquet`, table(daily));
      files.set(
        `${path}/universes/${universe}/summary.parquet`,
        table(periods),
      );
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
  if (task.task_type === "train")
    files.set(
      `${path}/models.json`,
      json({
        version: 1,
        task_type: "train",
        feature_protocol: { version: 1, task_type: "etl" },
        members: {
          model: {
            model_artifact: "model",
            model: { kind: "synthetic-model", strategy },
          },
        },
        artifacts: {
          model: {
            path: "model.json",
            size: files.get(`${path}/model.json`)!.size,
            revision: "1:1",
          },
        },
      }),
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
    reg_name: `playground.${task.task_type}`,
    source: { kind: "exec" },
    created_at: task.created_at,
    input_params: {
      ...task.input_params,
      task_name: task.reg_name,
      source_tasks: source.join(","),
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
              model_identity: { model: "synthetic" },
              dates,
              predictions_revision: "1:1",
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
  if (task.task_type === "backtest") {
    const { days, date_range, dimensions, evaluation_status, ...shared } =
      metadata.output_params;
    Object.assign(metadata, {
      output_params: {
        ...shared,
        signals_format: "stock-signals-v1",
        default_universe: "all",
        universes: Object.fromEntries(
          ["all", "hs300"].map((key) => [
            key,
            {
              label: key === "all" ? "All stocks" : "CSI 300",
              parameters: {},
              days,
              date_range,
              dimensions,
              evaluation_status,
              artifacts: { daily: `${key}_daily`, summary: `${key}_summary` },
            },
          ]),
        ),
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

export function seed() {
  const tasks = new Map<string, TaskMetadata>();
  const files = new Map<string, WorkspacePreview>();
  let source: string[] = [];
  for (const kind of [...kinds, "backtest"] as const) {
    const variant = tasks.has(`${kind}#demo`) ? "volatile" : "steady";
    const id = `${kind}#${variant === "steady" ? "demo" : "volatile"}`;
    const task = taskStatus(kind, id, `Demo ${kind} / ${variant}`);
    if (kind === "train") source = ["etl#demo"];
    if (kind === "backtest") source = ["predict#demo"];
    task.input_params.source_tasks = source.join(",");
    tasks.set(id, task);
    addArtifacts(files, task, variant, source);
    if (variant === "steady") source = [id];
  }
  seedOnline(tasks, files);
  seedNightly(tasks, files);
  for (const task of tasks.values()) {
    if (task.reg_name === "tushare_mins") task.category = "data_update";
  }
  for (const parent of tasks.values()) {
    for (const record of parent.children) {
      const child = record.task_id ? tasks.get(record.task_id) : undefined;
      if (child?.run_id === record.run_id) child.parent_run_id = parent.run_id;
    }
  }
  const download = taskStatus(
    "api",
    "api#playground_download#demo",
    "Synthetic data update",
  );
  download.category = "data_update";
  download.steps = [
    {
      parent: null,
      percentage: 100,
      group: "download",
      phase: "",
      label: "Download",
      scheduled_at: null,
      deadline: null,
      updated_at: epoch,
      files: {},
      error: "",
      metrics: {},
      name: "download",
      state: "done",
      started_at: epoch,
      finished_at: epoch,
      completed: 5100,
      total: 5100,
      unit: "symbols",
    },
  ];
  download.output_params = {
    rows: 5100,
    updated: "2026-01-05",
    status: "succeeded",
  };
  tasks.set(download.task_id, download);
  const scheduled = structuredClone(download);
  scheduled.task_id = "api#playground_download#scheduled";
  scheduled.run_id = "demo-data-run";
  scheduled.input_params.task_name = "Scheduled data update";
  tasks.set(scheduled.task_id, scheduled);
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
  failed.output_params = {};
  tasks.set(failed.task_id, failed);
  for (const task of tasks.values()) {
    const path = `${task.task_type}/${task.task_id}`;
    files.set(`${path}/metadata.json`, json(task));
    const rows = task.steps.map((step, index) => {
      const data = {
        kind: "progress",
        step: step.name,
        percentage: step.percentage,
      };
      return {
        line: index + 1,
        truncated: false,
        content: JSON.stringify(data),
        data,
        parse_error: null,
      };
    });
    files.set(`${path}/events.jsonl`, {
      kind: "jsonl",
      size: rows.reduce((size, row) => size + row.content.length + 1, 0),
      rows,
      offset: 0,
      limit: 200,
      has_more: false,
      truncated: false,
    });
  }
  return { tasks, files };
}

function seedOnline(
  tasks: Map<string, TaskMetadata>,
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
    const task = taskStatus(
      sample.kind as TaskMetadata["task_type"],
      id,
      sample.name,
    );
    task.report_kind = "online";
    task.input_params.task_name = sample.name;
    if (sample.kind === "analysis")
      task.input_params.comparison_keys = sample.result.comparisons?.map(
        (item) => item.key,
      );
    task.input_params.source_tasks =
      sample.kind === "analysis"
        ? "inference#playground_online#demo"
        : sample.kind === "inference"
          ? "api#playground_online#demo"
          : "";
    task.output_params = { ...sample.result, artifacts: {} };
    if (sample.kind === "inference") seedStockOnline(files, task);
    tasks.set(id, task);
    files.set(`${id.split("#")[0]}/${id}/metadata.json`, json(task));
  }
  const child = tasks.get("inference#playground_online#demo")!;
  const id = "composite#playground_online#demo";
  const parent = taskStatus("composite", id, "Synthetic online pipeline");
  parent.report_kind = "online_pipeline";
  parent.category = "online_prediction";
  parent.input_params = {
    task_name: "Synthetic online pipeline",
    trade_date: "2026-01-05",
  };
  parent.children = [
    {
      node_name: "model-1445",
      task: child.reg_name,
      task_id: child.task_id,
      run_id: child.run_id,
      attempt: 1,
      state: child.state,
      exit_code: 0,
      error: "",
    },
  ];
  const step: import("../shared/api/contracts").TaskStepStatus = {
    name: "collection:snapshot",
    label: "snapshot",
    parent: "execute",
    percentage: 100,
    group: "collection",
    state: "done",
    phase: "committed",
    completed: 5100,
    total: 5100,
    unit: "stocks",
    scheduled_at: epoch,
    deadline: epoch,
    started_at: epoch,
    finished_at: epoch,
    updated_at: epoch,
    metrics: { coverage: 0.998 },
    files: { data: "tushare/2026/20260105/rt/rt_k/data.csv" },
    error: "",
  };
  child.steps = [
    ...child.steps,
    ...[
      "initialization",
      "feature",
      "prediction",
      "portfolio",
      "publication",
    ].map((name) => ({
      ...step,
      name,
      label: name,
      parent: "run_windows",
      group: "inference",
      phase: "",
      completed: null,
      total: null,
      files: {},
      metrics: {},
    })),
  ];
  const collectionPath = "tushare/2026/20260105/rt/rt_k";
  const quality = {
    version: 1,
    trade_date: "20260105",
    trade_time: "0930",
    checks: [],
  };
  files.set(`${collectionPath}/data.csv`, {
    kind: "csv",
    size: 64,
    columns: ["ts_code", "price"],
    rows: [["DEMO001", 10.5]],
    offset: 0,
    limit: 200,
    has_more: false,
  });
  files.set(
    `${collectionPath}/metadata.json`,
    json({ trade_date: "20260105", trade_time: "0930" }),
  );
  files.set(`${collectionPath}/quality_summary.json`, json(quality));
  files.set(
    `${collectionPath}/quality_details.parquet`,
    table([{ ts_code: "DEMO001", status: "valid" }]),
  );
  step.files = Object.fromEntries(
    Object.entries({
      data: "data.csv",
      metadata: "metadata.json",
      quality_summary: "quality_summary.json",
      quality_details: "quality_details.parquet",
    }).map(([role, name]) => [
      role,
      `/demo/workspace/${collectionPath}/${name}`,
    ]),
  );
  parent.output_params.windows = [
    { key: "snapshot", status: "done", metrics: { quality } },
  ];
  parent.steps.push(step);
  parent.input_params.models = { "1445": [{ task_name: "demo" }] };
  parent.children[0].task = child.task_id.split("#")[1];
  parent.children[0].node_name = `demo-1445-${parent.children[0].task}`;
  tasks.set(id, parent);
  files.set(`${id.split("#")[0]}/${id}/metadata.json`, json(parent));
}

function seedNightly(
  tasks: Map<string, TaskMetadata>,
  files: Map<string, WorkspacePreview>,
) {
  const parent = taskStatus(
    "composite",
    "composite#playground_compare#demo",
    "Synthetic nightly comparison",
  );
  parent.report_kind = "compare_pipeline";
  parent.category = "comparison";
  parent.input_params = {
    task_name: "Synthetic nightly comparison",
    trade_date: "2026-01-05",
    trade_time: "1445",
    models: [
      { task_name: "nightly", feature_provider: "a_stock" },
      { task_name: "missing", feature_provider: "v1" },
    ],
  };
  const template = tasks
    .get("composite#playground_online#demo")!
    .steps.find((step) => step.parent)!;
  const step = (
    name: string,
    group: string,
    state: typeof template.state,
    error = "",
  ) => ({
    ...template,
    name,
    label: name.split(":").at(-1)!,
    group,
    state,
    phase: "",
    completed: null,
    total: null,
    metrics: {},
    files: {},
    error,
    scheduled_at: null,
    deadline: null,
  });
  const download = taskStatus(
    "composite",
    "composite#tushare_mins#nightly",
    "Synthetic nightly download",
  );
  const history = taskStatus(
    "composite",
    "composite#a_stock_history#nightly-1445",
    "Synthetic historical inputs",
  );
  const etl = taskStatus(
    "etl",
    "etl#a_stock_etl#nightly",
    "Synthetic historical features",
  );
  const comparison = taskStatus(
    "analysis",
    "analysis#a_stock_prediction_compare#nightly",
    "Synthetic comparison",
  );
  comparison.report_kind = "online";
  comparison.input_params.source_tasks = etl.task_id;
  comparison.output_params = {
    comparisons: [
      {
        key: "20260105/1445",
        status: "different",
        reason: "source_data_revised",
        metrics: {
          max_abs_diff: 0.0012,
          stages: Object.fromEntries(
            [
              "features",
              "market",
              "predictions",
              "ranking",
              "signals",
              "orders",
              "positions",
              "trades",
              "daily",
            ].map((key) => [
              key,
              {
                consistent: key !== "predictions",
                schema_equal: true,
                keys_equal: true,
                offline_rows: 5100,
                online_rows: 5100,
                mismatches: key === "predictions" ? { pred: 2 } : {},
                max_absolute_error:
                  key === "predictions" ? { pred: 0.0012 } : {},
              },
            ]),
          ),
        },
      },
    ],
  };
  const record = (task: TaskMetadata, node_name: string) => ({
    node_name,
    task: task.task_id.split("#")[1],
    task_id: task.task_id,
    run_id: task.run_id,
    attempt: 1,
    state: task.state,
    exit_code: 0,
    error: "",
  });
  history.children = [record(etl, "nightly-a_stock_etl")];
  history.steps = [step("history", "history", "done")];
  history.steps[0].phase = "rebuilt";
  parent.children = [
    record(download, "tushare_mins"),
    record(history, "nightly-1445-a_stock_history"),
    record(comparison, "nightly-a_stock_prediction_compare"),
  ];
  parent.steps = [
    step("download", "download", "done"),
    ...["nightly", "missing"].flatMap((model) =>
      ["etl", "online_source", "prediction", "comparison", "backtest"].map(
        (stage) =>
          step(
            `${model}:${stage}`,
            model,
            model === "missing" && stage !== "etl" ? "skipped" : "done",
            model === "missing" && stage !== "etl"
              ? "online_source_unavailable"
              : "",
          ),
      ),
    ),
  ];
  parent.output_params = {
    models: { nightly: { status: "done" }, missing: { status: "done" } },
  };
  for (const task of [parent, download, history, etl, comparison]) {
    task.output_params.artifacts = {};
    task.reg_name = task.task_id.split("#")[1];
    tasks.set(task.task_id, task);
    files.set(`${task.task_type}/${task.task_id}/metadata.json`, json(task));
  }
}

function seedStockOnline(
  files: Map<string, WorkspacePreview>,
  task: TaskMetadata,
) {
  const strategyIdentity = "a".repeat(64);
  const history: import("../features/online/report").OnlineHistory = {
    version: 1,
    task_type: "inference",
    kind: "online_history",
    strategy_identity: strategyIdentity,
    commits: [],
  };
  const allDaily = dailyRows("steady").slice(0, 12);
  for (let i = 0; i <= allDaily.length; i++) {
    const index = Math.min(i, allDaily.length - 1);
    const date = allDaily[index].trade_date;
    const commitId = (i + 1).toString(16).padStart(32, "0");
    const signal = Array.from({ length: 30 }, (_, rank) => ({
      trade_date: date,
      trade_time: "1445",
      ts_code: `DEMO${String(rank + 1).padStart(3, "0")}`,
      name: `Synthetic ${rank + 1}`,
      pred: (30 - rank) / 100 + index / 1000,
      pred_seed_0: (30 - rank) / 100 + index / 1000,
      rank: rank + 1,
      buyable_rank: rank % 7 === 0 ? null : rank + 1 - Math.ceil(rank / 7),
      is_buyable_at_signal: rank % 7 !== 0,
      is_model_candidate: true,
      signal_price: 10 + rank * 1.25,
      signal_adjustment_factor: 1,
    }));
    let net = 1;
    const daily = allDaily.slice(0, index + 1).map((row) => {
      net *= 1 + Number(row.top5_net_return);
      return {
        ...row,
        top5_net_value: net,
        top10_net_value: net,
        top5_cash_weight: 0.04,
        top10_cash_weight: 0.04,
        top5_count: 5,
        top10_count: 10,
        top5_transaction_cost: 0.0002,
        top10_transaction_cost: 0.0002,
      };
    });
    const portfolio = {
      top_ns: [5, 10],
      holding_days: 3,
      score_aggregation: "mean",
      missing_market_as_suspension: false,
      buy_cost_rate: 0.0005,
      sell_cost_rate: 0.0015,
    };
    const settings: import("../features/online/report").ReportSettings = {
      signals_format: "stock-signals-v1",
      strategy_identity: strategyIdentity,
      dimensions: {
        top_ns: [5, 10],
        holding_detail_top_n: 30,
        benchmarks: [{ key: "demo", label: "Synthetic benchmark" }],
      },
      date_range: { start: allDaily[0].trade_date, end: date },
      portfolio,
      score_selection: { method: "mean", seeds: [0] },
      evaluation_status: "done",
      missing_dates: [],
    };
    const tables: Record<string, Record<string, unknown>[]> = {
      signal,
      signals: signal.map((row) => ({
        ...row,
        is_backtest_candidate: row.is_buyable_at_signal,
        target_rank: row.is_buyable_at_signal ? row.buyable_rank : null,
        label_return: null,
      })),
      predictions: signal,
      market: signal,
      daily,
      summary: [
        {
          period_type: "overall",
          period: "overall",
          trading_days: index + 1,
          top5_net_annualized_return: 0.16,
          top10_net_annualized_return: 0.14,
          top5_gross_sharpe: 1.8,
          top10_gross_sharpe: 1.7,
          top5_net_max_drawdown: -0.022,
          top10_net_max_drawdown: -0.02,
        },
      ],
      positions: [5, 10].flatMap((n) =>
        signal.slice(1, n + 1).map((row) => ({
          top_n: n,
          trade_date: date,
          ts_code: row.ts_code,
          entry_date: allDaily[Math.max(0, index - 2)].trade_date,
          planned_exit_date: null,
          weight: 0.96 / n,
          market_value: (net * 0.96) / n,
          exit_delayed: false,
        })),
      ),
      orders: [5, 10].flatMap((n) => [
        {
          top_n: n,
          trade_date: date,
          ts_code: "DEMO002",
          side: "buy",
          status: "filled",
          reason: "",
          notional: 0.96 / n,
          fee: (0.0005 * 0.96) / n,
        },
        {
          top_n: n,
          trade_date: date,
          ts_code: "DEMO008",
          side: "buy",
          status: "unfilled",
          reason: "not_buyable",
          notional: 0,
          fee: 0,
        },
      ]),
      trades: [5, 10].map((n) => ({
        top_n: n,
        ts_code: "DEMO003",
        entry_date: allDaily[0].trade_date,
        exit_date: date,
        realized_return: 0.012,
        fee: 0.0003,
      })),
      calendar: allDaily.map((row) => ({ trade_date: row.trade_date })),
      input_features: signal,
    };
    const artifacts: Record<
      string,
      { path: string; size: number; revision: string }
    > = {};
    const put = (role: string, preview: WorkspacePreview, suffix: string) => {
      const path = `persistent/online/commits/${commitId}/${role}.${suffix}`;
      artifacts[role] = { path, size: preview.size, revision: "1:1" };
      files.set(`inference/${task.task_id}/${path}`, preview);
    };
    for (const [role, rows] of Object.entries(tables))
      put(role, table(rows), "parquet");
    const quality = {
      version: 1,
      trade_date: date,
      trade_time: "1445",
      checks: [
        {
          stage: "collection/1445_bar",
          reason: "missing_slots",
          action: "warning",
          input_count: 35,
          output_count: 35,
          matched_count: 5,
          removed_count: 0,
          coverage: 30 / 35,
          threshold: 0.8,
          samples: [{ ts_code: "DEMO031", missing_slots: "1445" }],
        },
        {
          stage: "prediction",
          reason: "not_buyable",
          action: "unbuyable",
          input_count: 30,
          output_count: 30,
          matched_count: 5,
          removed_count: 0,
          samples: [{ ts_code: "DEMO001", is_limit_up: true }],
        },
      ],
    };
    put("quality_summary", json(quality), "json");
    put(
      "quality_details",
      table([
        {
          stage: "collection/1445_bar",
          reason: "missing_slots",
          action: "warning",
          ts_code: "DEMO031",
          details: JSON.stringify({ missing_slots: "1445" }),
        },
        {
          stage: "prediction",
          reason: "not_buyable",
          action: "unbuyable",
          ts_code: "DEMO001",
          details: JSON.stringify({ is_limit_up: true }),
        },
      ]),
      "parquet",
    );
    const identity = {
      family: "synthetic",
      models_sha256: "c".repeat(64),
      features_sha256: "d".repeat(64),
      trade_time: "1445",
    };
    const protocol = {
      version: 1,
      task_type: "inference",
      model_identity: identity,
      dates: [date],
      score_columns: { seed_0: "pred_seed_0" },
      predictions_revision: "1:1",
      portfolio,
      report: settings,
    };
    put("prediction_protocol", json(protocol), "json");
    history.commits.push({
      commit_id: commitId,
      task_id: task.task_id,
      run_id: `demo-run-${i}`,
      trade_date: date,
      trade_time: "1445",
      revision: i === allDaily.length ? 2 : 1,
      committed_at: `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}T14:45:10+08:00`,
      model_identity: identity,
      protocol,
      artifacts,
    });
  }
  const commit = history.commits.at(-1)!;
  task.run_id = commit.run_id;
  const historyPath = `persistent/online/commits/${commit.commit_id}/history.json`;
  files.set(`inference/${task.task_id}/${historyPath}`, json(history));
  files.set(
    `inference/${task.task_id}/persistent/online/manifest.json`,
    json(history),
  );
  task.output_params = {
    model_identity: commit.model_identity,
    windows: [
      {
        key: "1445",
        status: "done",
        rows: 30,
        elapsed_seconds: 4.2,
        commit_id: commit.commit_id,
        committed_at: commit.committed_at,
        metrics: {
          feature_seconds: 2.8,
          prediction_seconds: 0.9,
          candidate_count: 30,
          buyable_count: 25,
        },
      },
    ],
    report: { kind: "stock_online", commit },
    artifacts: {
      ...commit.artifacts,
      signal_history: { path: historyPath, size: 1, revision: "1:1" },
    },
  };
}
