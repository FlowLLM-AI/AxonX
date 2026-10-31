import { taskDirectory } from "../shared/lib/tasks";
import type { TaskMetadata } from "../shared/api/contracts";
import type { WorkspacePreview } from "../shared/api/workspace";
import { json, taskStatus } from "./data";

export function seedNightly(
  tasks: Map<string, TaskMetadata>,
  files: Map<string, WorkspacePreview>,
) {
  const parent = taskStatus("base", "base#playground_compare#demo");
  parent.report_kind = "compare_pipeline";
  parent.input_params = {
    task_name: "demo",
    trade_date: "2026-01-05",
    models: {
      "0945": [{ task_name: "morning", train: { reg_name: "a_stock_train" } }],
      "1445": [
        {
          task_name: "nightly",
          train: { reg_name: "a_stock_train" },
          predict: { reg_name: "a_stock_predict" },
          portfolio: { reg_name: "a_stock_portfolio" },
          compare: { reg_name: "a_stock_prediction_compare" },
        },
        {
          task_name: "missing",
          etl: [
            { reg_name: "v1_merge", params: {} },
            { reg_name: "v1_feature", params: {} },
          ],
          train: { reg_name: "v1_train", params: {} },
          predict: { reg_name: "v1_predict", params: {} },
          portfolio: {
            reg_name: "v1_portfolio",
            params: {
              universes: [{ kind: "all" }],
              top_ns: [10],
              holding_days: 10,
            },
          },
          compare: { reg_name: "a_stock_prediction_compare", params: {} },
        },
      ],
    },
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
  const download = taskStatus("base", "base#tushare_mins#nightly");
  const history = taskStatus("base", "base#a_stock_history#nightly-1445");
  const etl = taskStatus("etl", "etl#a_stock_etl#nightly");
  const comparison = taskStatus(
    "analysis",
    "analysis#a_stock_prediction_compare#nightly",
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
    record(comparison, "nightly-1445-a_stock_prediction_compare"),
  ];
  parent.steps = [
    step("download", "download", "done"),
    ...["nightly", "missing"].flatMap((model) =>
      ["etl", "online_source", "prediction", "portfolio", "comparison"].map(
        (stage) =>
          step(
            `${model}-1445:${stage}`,
            `${model}-1445`,
            model === "missing" && stage !== "etl" ? "skipped" : "done",
            model === "missing" && stage !== "etl"
              ? "online_source_unavailable"
              : "",
          ),
      ),
    ),
  ];
  parent.output_params = {
    models: {
      "0945": {
        morning: {
          status: "done",
          comparison: {
            status: "skipped",
            reason: "online_source_unavailable",
          },
        },
      },
      "1445": { nightly: { status: "done" }, missing: { status: "done" } },
    },
  };
  for (const task of [parent, download, history, etl, comparison]) {
    task.output_params.artifacts = {};
    task.reg_name = task.task_id.split("#")[1];
    tasks.set(task.task_id, task);
    files.set(`${taskDirectory(task.task_id)}/metadata.json`, json(task));
  }
}
