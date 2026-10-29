import { taskDirectory } from "../shared/lib/tasks";
import type { TaskMetadata } from "../shared/api/contracts";
import type { WorkspacePreview } from "../shared/api/workspace";
import { dailyRows, epoch, json, table, taskStatus } from "./data";

export function seedOnline(
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
    const task = taskStatus(sample.kind as TaskMetadata["task_type"], id);
    task.report_kind = "online";
    if (sample.kind === "analysis")
      task.input_params.comparison_keys = sample.result.comparisons?.map(
        (item) => item.key,
      );
    task.input_params.upstream_task_ids =
      sample.kind === "analysis"
        ? ["inference#playground_online#demo"]
        : sample.kind === "inference"
          ? ["api#playground_online#demo"]
          : [];
    task.output_params = { ...sample.result, artifacts: {} };
    if (sample.kind === "inference") seedStockOnline(files, task);
    tasks.set(id, task);
    files.set(`${taskDirectory(id)}/metadata.json`, json(task));
  }
  const child = tasks.get("inference#playground_online#demo")!;
  const id = "base#playground_online#demo";
  const parent = taskStatus("base", id);
  parent.report_kind = "online_pipeline";
  parent.input_params = {
    task_name: "demo",
    trade_date: "2026-01-05",
  };
  parent.children = [
    {
      node_name: "model-1445",
      reg_name: child.reg_name,
      child_task_id: child.task_id,
      started_at: child.started_at,
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
  parent.children[0].reg_name = child.task_id.split("#")[1];
  parent.children[0].node_name = `demo-1445-${parent.children[0].reg_name}`;
  tasks.set(id, parent);
  files.set(`${taskDirectory(id)}/metadata.json`, json(parent));
}

function seedStockOnline(
  files: Map<string, WorkspacePreview>,
  task: TaskMetadata,
) {
  const strategyIdentity = "a".repeat(64);
  const history: import("../features/operations/report").OnlineHistory = {
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
    const settings: import("../features/operations/report").ReportSettings = {
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
      files.set(`${taskDirectory(task.task_id)}/${path}`, preview);
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
      started_at: `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}T14:45:00+08:00`,
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
  task.started_at = commit.started_at;
  task.finished_at = commit.committed_at;
  const historyPath = `persistent/online/commits/${commit.commit_id}/history.json`;
  files.set(`${taskDirectory(task.task_id)}/${historyPath}`, json(history));
  files.set(
    `${taskDirectory(task.task_id)}/persistent/online/manifest.json`,
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
