import type { TaskMetadata } from "../shared/api/contracts";
import type { WorkspacePreview } from "../shared/api/workspace";
import { json, taskStatus } from "./data";

export function seedNightly(
  tasks: Map<string, TaskMetadata>,
  files: Map<string, WorkspacePreview>,
) {
  const parent = taskStatus(
    "base",
    "base#playground_compare#demo",
    "Synthetic nightly comparison",
  );
  parent.report_kind = "compare_pipeline";
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
    .get("base#playground_online#demo")!
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
    "base",
    "base#tushare_mins#nightly",
    "Synthetic nightly download",
  );
  const history = taskStatus(
    "base",
    "base#a_stock_history#nightly-1445",
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
  comparison.input_params.upstream_task_ids = [etl.task_id];
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
    reg_name: task.task_id.split("#")[1],
    child_task_id: task.task_id,
    started_at: task.started_at,
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
