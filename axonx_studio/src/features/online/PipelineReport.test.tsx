// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { PipelineReport } from "./PipelineReport";
import { getTaskStatus, readTaskLog } from "../tasks/api";
import type { TaskMetadata, TaskSummary } from "../tasks/types";

vi.mock("../tasks/api", () => ({
  getTaskStatus: vi.fn(),
  readTaskLog: vi.fn(),
}));
let root: Root;
let container: HTMLDivElement;
let parent: TaskMetadata;
let child: TaskMetadata;
const target = "http://selected-machine";
beforeEach(() => {
  vi.clearAllMocks();
  const tasks = seed().tasks;
  parent = structuredClone(tasks.get("composite#playground_online#demo")!);
  child = structuredClone(tasks.get("inference#playground_online#demo")!);
  parent.state = "running";
  parent.children[0].state = "running";
  child.state = "running";
  child.output_params = {};
  child.steps = [
    {
      ...child.steps[0],
      name: "feature",
      label: "feature",
      parent: "run_windows",
      group: "inference",
      state: "running",
      percentage: null,
      started_at: null,
      finished_at: null,
    },
  ];
  vi.mocked(getTaskStatus).mockImplementation(async (id) =>
    id === parent.task_id ? parent : child,
  );
  vi.mocked(readTaskLog).mockResolvedValue({
    content: "parent download log",
    start_offset: 0,
    next_offset: 19,
    file_size: 19,
    has_more_before: false,
    has_more_after: false,
    reset: false,
  });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async () =>
  act(async () =>
    root.render(
      <PipelineReport
        task={
          {
            ...parent,
            display_name: "online",
            is_replica: false,
            step_progress: null,
            is_online: true,
          } as TaskSummary
        }
        target={target}
        onOpenTask={vi.fn()}
      />,
    ),
  );

it("shows live stages and committed files, and switches logs on the selected machine", async () => {
  await render();
  expect(container.textContent).toContain("99.8%");
  expect(container.querySelector("details[open]")?.textContent).toMatch(
    /feature|特征/,
  );
  expect(container.textContent).toContain("data.csv");
  expect(container.querySelector(".log-content")?.textContent).toContain(
    "parent download log",
  );
  const select = container.querySelector<HTMLSelectElement>(
    ".pipeline-log-source select",
  )!;
  await act(async () => {
    select.value = child.task_id;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(
    vi
      .mocked(readTaskLog)
      .mock.calls.some(
        (call) => call[0] === child.task_id && call[3] === target,
      ),
  ).toBe(true);
  expect(
    vi.mocked(getTaskStatus).mock.calls.every((call) => call[1] === target),
  ).toBe(true);
});

it("does not display stages or logs from a child replacement Run", async () => {
  child.run_id = "replacement-run";
  await render();
  expect(
    container.querySelector(".pipeline-log-source select")?.children,
  ).toHaveLength(1);
  expect(container.querySelector(".error-state")).not.toBeNull();
  expect(container.querySelector(".pipeline-model details")).toBeNull();
});

it("keeps progress visible when a child has a malformed report", async () => {
  child.output_params = { report: { malformed: true } };
  await render();
  expect(container.textContent).toContain("99.8%");
  expect(container.querySelector(".error-state")?.textContent).toContain(
    "Error",
  );
  expect(container.querySelector(".pipeline-model details")).not.toBeNull();
});

it("uses the latest named child attempt without duplicating the model count", async () => {
  const latest = { ...parent.children[0], attempt: 2, run_id: child.run_id };
  parent.children[0] = {
    ...latest,
    attempt: 1,
    state: "succeeded",
    run_id: "old-run",
  };
  parent.children.push(latest);
  await render();
  expect(container.querySelector(".pipeline-model details")).not.toBeNull();
  expect(container.querySelector(".error-state")).toBeNull();
  expect(
    vi
      .mocked(getTaskStatus)
      .mock.calls.filter((call) => call[0] === child.task_id),
  ).toHaveLength(1);
});

it("shows the business reason when a missed input window never started a child", async () => {
  parent.state = "failed";
  parent.children = [];
  parent.output_params.models = {
    "1445": { status: "missed", reason: "data_not_ready_before_deadline" },
  };
  await render();
  const model = container.querySelector(".pipeline-model");
  expect(model?.textContent).toContain(
    i18n.t("onlinePipeline.reasons.data_not_ready_before_deadline"),
  );
  expect(model?.querySelector("details")).toBeNull();
});

it("shows nightly model plans, skipped comparisons and nested history task logs", async () => {
  parent.report_kind = "compare_pipeline";
  parent.input_params = {
    models: [{ task_name: "demo", feature_provider: "a_stock" }],
    trade_time: "1445",
  };
  parent.steps = [
    {
      ...child.steps[0],
      name: "demo:etl",
      group: "demo",
      label: "etl",
      state: "done",
    },
    {
      ...child.steps[0],
      name: "demo:comparison",
      group: "demo",
      label: "comparison",
      state: "skipped",
      error: "online_source_unavailable",
    },
  ];
  parent.output_params = {
    models: { demo: { status: "done", comparison: { status: "skipped" } } },
  };
  const history = structuredClone(child);
  history.task_id = "composite#a_stock_history#demo-1445";
  history.run_id = "history-run";
  history.reg_name = "a_stock_history";
  history.task_type = "composite";
  history.report_kind = null;
  history.input_params.task_name = "demo-1445";
  const etl = structuredClone(child);
  etl.task_id = "etl#a_stock_etl#demo";
  etl.run_id = "etl-run";
  etl.reg_name = "a_stock_etl";
  etl.report_kind = null;
  etl.task_type = "etl";
  etl.children = [];
  history.children = [
    {
      ...parent.children[0],
      task: etl.reg_name,
      task_id: etl.task_id,
      run_id: etl.run_id,
      node_name: "demo-a_stock_etl",
    },
  ];
  parent.children = [
    {
      ...parent.children[0],
      task: history.reg_name,
      task_id: history.task_id,
      run_id: history.run_id,
      node_name: "demo-1445-a_stock_history",
    },
  ];
  const tasks = new Map(
    [parent, history, etl].map((task) => [task.task_id, task]),
  );
  vi.mocked(getTaskStatus).mockImplementation(async (id) => tasks.get(id)!);
  await render();
  expect(container.textContent).toContain(i18n.t("onlinePipeline.nightly"));
  expect(container.textContent).toContain(
    i18n.t("onlinePipeline.reasons.online_source_unavailable"),
  );
  expect(container.textContent).toContain("demo-a_stock_etl");
  expect(
    container.querySelector(".pipeline-log-source select")?.children,
  ).toHaveLength(3);
  const select = container.querySelector<HTMLSelectElement>(
    ".pipeline-log-source select",
  )!;
  await act(async () => {
    select.value = etl.task_id;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(
    vi
      .mocked(readTaskLog)
      .mock.calls.some((call) => call[0] === etl.task_id && call[3] === target),
  ).toBe(true);
});

it("keeps nightly stages visible when a comparison report is malformed", async () => {
  parent.report_kind = "compare_pipeline";
  parent.input_params = {
    models: [{ task_name: "demo", feature_provider: "a_stock" }],
    trade_time: "1445",
  };
  child.reg_name = "a_stock_prediction_compare";
  child.report_kind = "online";
  child.output_params = { comparisons: [{ key: "bad", status: "invalid" }] };
  parent.children[0].task = child.reg_name;
  parent.children[0].node_name = "demo-a_stock_prediction_compare";
  await render();
  expect(container.textContent).toContain(i18n.t("onlinePipeline.nightly"));
  expect(container.textContent).toContain("Invalid online report");
});

it("settles unfinished nightly model summaries after download failure and cancellation", async () => {
  parent.report_kind = "compare_pipeline";
  parent.input_params = {
    models: [{ task_name: "demo", feature_provider: "a_stock" }],
    trade_time: "1445",
  };
  parent.output_params = { models: { demo: { status: "pending" } } };
  parent.children = [];
  parent.steps = [];
  parent.state = "failed";
  await render();
  expect(
    container.querySelector(".pipeline-model header")?.textContent,
  ).toContain(i18n.t("onlinePipeline.status.skipped"));
  parent.state = "cancelled";
  // A new selection reloads the lifecycle snapshot.
  parent.run_id = "cancelled-run";
  await render();
  expect(
    container.querySelector(".pipeline-model header")?.textContent,
  ).toContain(i18n.t("onlinePipeline.status.cancelled"));
});
