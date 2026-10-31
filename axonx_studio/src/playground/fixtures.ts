import { taskDirectory } from "../shared/lib/tasks";
import type { TaskMetadata } from "../shared/api/contracts";
import type { WorkspacePreview } from "../shared/api/workspace";
import { seedNightly } from "./comparison";
import {
  addArtifacts,
  dailyRows,
  epoch,
  json,
  kinds,
  table,
  taskStatus,
} from "./data";
import { seedOnline } from "./online";

export function seed() {
  const tasks = new Map<string, TaskMetadata>();
  const files = new Map<string, WorkspacePreview>();
  const sourceFiles = new Map<string, string>();
  let upstreamIds: string[] = [];
  for (const kind of [...kinds, "backtest"] as const) {
    const variant = tasks.has(`${kind}#playground_${kind}#demo`)
      ? "volatile"
      : "steady";
    const id = `${kind}#playground_${kind}#${variant === "steady" ? "demo" : "volatile"}`;
    const task = taskStatus(kind, id);
    if (kind === "train") upstreamIds = ["etl#playground_etl#demo"];
    if (kind === "backtest")
      upstreamIds = ["portfolio#playground_portfolio#demo"];
    task.input_params.upstream_task_ids = [...upstreamIds];
    tasks.set(id, task);
    addArtifacts(files, task, variant, upstreamIds);
    if (variant === "steady") upstreamIds = [id];
  }
  seedOnline(tasks, files);
  for (const task of tasks.values()) {
    if (task.task_type !== "portfolio") continue;
    const id = (task.input_params.upstream_task_ids as string[]).find((id) =>
      id.startsWith("predict#"),
    )!;
    const source = tasks.get(id)!;
    task.input_sources[id] = {
      started_at: source.started_at,
      artifacts: {
        predictions: (
          source.output_params.artifacts as Record<
            string,
            import("../shared/api/contracts").ArtifactRecord
          >
        ).predictions,
      },
    };
    files.set(`${taskDirectory(task.task_id)}/metadata.json`, json(task));
  }
  seedNightly(tasks, files);
  for (const task of tasks.values()) {
    if (task.reg_name === "tushare_mins") task.report_kind = "data_update";
  }
  for (const parent of tasks.values()) {
    for (const record of parent.children) {
      const child = record.child_task_id
        ? tasks.get(record.child_task_id)
        : undefined;
      if (child?.started_at === record.started_at)
        child.parent_task_id = parent.task_id;
    }
  }
  const download = taskStatus("api", "api#playground_download#demo");
  download.report_kind = "data_update";
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
  scheduled.started_at = "2026-01-06T00:00:00Z";
  scheduled.finished_at = scheduled.started_at;
  scheduled.input_params.task_name = "scheduled";
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
  const markdown =
    "# Synthetic market data / 合成行情\n\nAll securities, returns and results are fictional. / 所有证券、收益和结果均为虚构。";
  const frontmatter = {
    title: "Synthetic market data",
    tags: ["market", "simulation"],
    simulated: true,
  };
  const source = `---\ntitle: "Synthetic market data" # demo metadata\ntags: [market, simulation]\nsimulated: true\n---\n${markdown}`;
  sourceFiles.set("tushare/README.md", source);
  files.set("tushare/README.md", {
    kind: "markdown",
    content: markdown,
    size: new TextEncoder().encode(source).length,
    truncated: false,
    frontmatter,
    frontmatter_error: null,
  });
  const failed = taskStatus("train", "train#playground_train#failed");
  failed.state = "failed";
  failed.error = "Simulated missing input";
  failed.exit_code = 1;
  failed.output_params = {};
  tasks.set(failed.task_id, failed);
  for (const task of tasks.values()) {
    const path = taskDirectory(task.task_id);
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
  return { tasks, files, sourceFiles };
}
