// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { HistoryPreparation } from "./HistoryPreparation";
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
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
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
  vi.unstubAllGlobals();
});
const render = async () => {
  await act(async () =>
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
};

const clickTab = async (id: string) =>
  act(async () =>
    container
      .querySelector<HTMLButtonElement>(`[role="tab"][id$="-${id}-tab"]`)!
      .click(),
  );

it("shows live stages, committed files and the selected inference log on the selected machine", async () => {
  await render();
  expect(container.textContent).toContain("99.8%");
  await clickTab("1445");
  await clickTab("preparation");
  expect(
    container.querySelector(".pipeline-model-content")?.textContent,
  ).toMatch(/feature|特征/);
  await clickTab("data");
  expect(container.textContent).toContain("data.csv");
  await clickTab("1445");
  await clickTab("logs");
  expect(container.querySelector(".log-content")?.textContent).toContain(
    "parent download log",
  );
  expect(container.querySelector(".pipeline-log-source select")).toBeNull();
  expect(
    container.querySelector(".daily-log-caption")?.getAttribute("title"),
  ).toBe(child.task_id);
  expect(
    vi
      .mocked(readTaskLog)
      .mock.calls.some(
        (call) =>
          call[0] === child.task_id &&
          call[3] === target &&
          call[5] === child.run_id,
      ),
  ).toBe(true);
  expect(
    vi.mocked(getTaskStatus).mock.calls.every((call) => call[1] === target),
  ).toBe(true);
});

it("does not display stages or logs from a child replacement Run", async () => {
  child.run_id = "replacement-run";
  await render();
  await clickTab("logs");
  expect(container.querySelector(".pipeline-log-source select")).toBeNull();
  expect(container.querySelector(".daily-log-caption")?.textContent).toContain(
    i18n.t("onlinePipeline.chainLog"),
  );
  expect(
    vi
      .mocked(readTaskLog)
      .mock.calls.every((call) => call[0] !== child.task_id),
  ).toBe(true);
  expect(container.querySelector(".task-run-notice")).not.toBeNull();
  expect(container.textContent).not.toContain(
    i18n.t("onlinePipeline.replacedRun"),
  );
  await clickTab("1445");
  await clickTab("preparation");
  expect(container.querySelector(".online-stage-heading")).toBeNull();
});

it("keeps progress visible when a child has a malformed report", async () => {
  child.output_params = { report: { malformed: true } };
  await render();
  expect(container.textContent).toContain("99.8%");
  expect(container.querySelector(".error-state")?.textContent).toContain(
    "Error",
  );
  await clickTab("1445");
  await clickTab("preparation");
  expect(container.querySelector(".pipeline-model-content")).not.toBeNull();
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
  await clickTab("1445");
  await clickTab("preparation");
  expect(container.querySelector(".pipeline-model-content")).not.toBeNull();
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
  await clickTab("1445");
  await clickTab("results");
  const model = container.querySelector(".pipeline-model-content");
  expect(model?.textContent).toContain(
    i18n.t("onlinePipeline.reasons.data_not_ready_before_deadline"),
  );
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
  await clickTab("results");
  expect(container.textContent).toContain(
    i18n.t("onlinePipeline.reasons.online_source_unavailable"),
  );
  await clickTab("etl");
  expect(container.textContent).toContain("demo-a_stock_etl");
  expect(
    container.querySelector(".pipeline-log-source select")?.children,
  ).toHaveLength(2);
  const select = container.querySelector<HTMLSelectElement>(
    ".pipeline-log-source select",
  )!;
  await act(async () => {
    select.value = `${etl.task_id}:${etl.run_id}`;
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
  await clickTab("results");
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
  await clickTab("etl");
  expect(
    container.querySelector(".compare-active-model")?.textContent,
  ).toContain(i18n.t("onlinePipeline.status.skipped"));
  parent.state = "cancelled";
  // A new selection reloads the lifecycle snapshot.
  parent.run_id = "cancelled-run";
  await render();
  await clickTab("etl");
  expect(
    container.querySelector(".compare-active-model")?.textContent,
  ).toContain(i18n.t("onlinePipeline.status.cancelled"));
});

it("refreshes details and logs every 60 seconds while preserving the selected tab", async () => {
  vi.useFakeTimers();
  try {
    await render();
    await clickTab("logs");
    expect(
      container
        .querySelector('[role="tab"][id$="-logs-tab"]')
        ?.getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      container
        .querySelector('[role="tab"][id$="-collection-tab"]')
        ?.getAttribute("aria-selected"),
    ).toBe("false");
    const initial = vi.mocked(getTaskStatus).mock.calls.length;
    const initialLogs = vi.mocked(readTaskLog).mock.calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(59_000));
    expect(getTaskStatus).toHaveBeenCalledTimes(initial);
    expect(readTaskLog).toHaveBeenCalledTimes(initialLogs);
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    expect(vi.mocked(getTaskStatus).mock.calls.length).toBeGreaterThan(initial);
    expect(vi.mocked(readTaskLog).mock.calls.length).toBeGreaterThan(
      initialLogs,
    );
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>(
          '[role="tab"][id$="-collection-tab"]',
        )!
        .click(),
    );
    const beforeRefresh = vi.mocked(getTaskStatus).mock.calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(vi.mocked(getTaskStatus).mock.calls.length).toBeGreaterThan(
      beforeRefresh,
    );
    expect(
      container
        .querySelector('[role="tab"][id$="-logs-tab"]')
        ?.getAttribute("aria-selected"),
    ).toBe("false");
  } finally {
    vi.useRealTimers();
  }
});

it("flattens quality into the second navigation row and preserves workspace file links", async () => {
  const previousHash = window.location.hash;
  window.location.hash = "#machine-b/operations/online";
  try {
    parent.output_params.windows = [
      {
        key: "snapshot",
        status: "done",
        metrics: {
          quality: {
            version: 1,
            trade_date: "20261019",
            trade_time: "0930",
            checks: [],
          },
        },
      },
    ];
    await render();
    const card = container.querySelector(".pipeline-step.step-done")!;
    expect(card.querySelectorAll(".online-quality-window")).toHaveLength(0);
    expect(card.querySelector("details")).toBeNull();
    expect(card.querySelectorAll('[role="tab"]')).toHaveLength(0);
    expect(card.querySelector("button")).toBeNull();
    await clickTab("quality-snapshot");
    expect(container.querySelectorAll(".online-quality-window")).toHaveLength(
      1,
    );
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelectorAll('[role="tablist"]')).toHaveLength(2);
    const file = card.querySelector<HTMLAnchorElement>(
      ".pipeline-step-files a",
    )!;
    expect(file.textContent).toContain("data.csv");
    expect(file.getAttribute("href")).toBe(
      "#machine-b/workspace/files/" +
        encodeURIComponent(
          parent.steps.find((step) => step.group === "collection")!.files!.data,
        ),
    );
  } finally {
    window.location.hash = previousHash;
  }
});

it("joins history parent progress and its child stages into one card per model", async () => {
  const record = {
    ...parent.children[0],
    task: "a_stock_history",
    node_name: "default-0945-0945-a_stock_history",
    task_id: "composite#history#demo",
    state: "succeeded" as const,
  };
  const step = {
    ...child.steps[0],
    name: "history:default-0945-0945",
    group: "history",
    state: "done" as const,
  };
  parent.children = [record];
  parent.steps = [
    step,
    { ...step, name: "history:default-1000-1000", state: "pending" },
  ];
  child.steps = [
    { ...child.steps[0], name: "prepare_history", label: "prepare_history" },
  ];
  const onOpenTask = vi.fn();
  await act(async () =>
    root.render(
      <HistoryPreparation
        parent={parent}
        nodes={[{ record, status: child, error: "" }]}
        onOpenTask={onOpenTask}
      />,
    ),
  );
  expect(container.querySelectorAll(".history-preparation-card")).toHaveLength(
    2,
  );
  expect(
    container.querySelector(".history-preparation-card")?.textContent,
  ).toContain("prepare_history");
  expect(
    container.querySelector(".history-preparation-card")?.textContent,
  ).not.toContain(record.node_name);
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>(".history-preparation-actions button")!
      .click(),
  );
  expect(onOpenTask).toHaveBeenCalledWith(record.task_id);
});

it("keeps history failure and exact-run replacement errors in the same card", async () => {
  const record = {
    ...parent.children[0],
    task: "a_stock_history",
    node_name: "default-0945-0945-a_stock_history",
    task_id: "composite#history#demo",
  };
  parent.children = [record];
  parent.steps = [
    {
      ...child.steps[0],
      name: "history:default-0945-0945",
      group: "history",
      state: "failed",
      error: "Source task failed",
    },
  ];
  await act(async () =>
    root.render(
      <HistoryPreparation
        parent={parent}
        nodes={[{ record, status: null, error: "Run replaced" }]}
        onOpenTask={vi.fn()}
      />,
    ),
  );
  expect(container.querySelectorAll(".history-preparation-card")).toHaveLength(
    1,
  );
  expect(container.querySelector(".step-failed")?.textContent).toContain(
    "Source task failed",
  );
  expect(container.textContent).toContain("Run replaced");
  expect(container.querySelector(".history-preparation-stages")).toBeNull();
});

it("summarizes completed history reuse in one row while retaining failed stage details", async () => {
  const record = {
    ...parent.children[0],
    task: "a_stock_history",
    node_name: "demo-1445-a_stock_history",
    task_id: "composite#history#demo",
    state: "succeeded" as const,
  };
  parent.children = [record];
  parent.steps = [
    {
      ...child.steps[0],
      name: "history:demo-1445",
      group: "history",
      state: "done",
    },
  ];
  child.steps = [
    {
      ...child.steps[0],
      name: "history",
      label: "prepare_history",
      state: "done",
      phase: "reused",
      metrics: {},
      files: {},
      completed: null,
      total: null,
    },
  ];
  const renderHistory = () =>
    act(async () =>
      root.render(
        <HistoryPreparation
          parent={parent}
          nodes={[{ record, status: child, error: "" }]}
          modelName="demo"
          slot="1445"
          onOpenTask={vi.fn()}
        />,
      ),
    );
  await renderHistory();
  expect(container.textContent).toContain(
    i18n.t("onlinePipeline.phases.reused"),
  );
  expect(container.querySelectorAll(".online-status")).toHaveLength(1);
  expect(container.querySelector(".history-preparation-stages")).toBeNull();
  child.steps[0].state = "failed";
  child.steps[0].error = "History read failed";
  await renderHistory();
  expect(
    container.querySelector(".history-preparation-stages")?.textContent,
  ).toContain("History read failed");
});
