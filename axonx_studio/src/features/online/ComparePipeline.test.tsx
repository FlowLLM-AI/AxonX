// @vitest-environment jsdom
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { ComparePipeline } from "./ComparePipeline";
import { compareModels, ownedCompareNodes } from "./compare";
import type { TaskMetadata } from "../tasks/types";
import type { TaskNode } from "../tasks/tree";

vi.mock("../tasks/TaskLogPanel", () => ({
  TaskLogPanel: ({
    task,
    target,
    toolbar,
  }: {
    task: TaskMetadata;
    target?: string;
    toolbar?: ReactNode;
  }) => (
    <div>
      {toolbar}
      <pre data-run={task.run_id} data-target={target}>
        {task.task_id}
      </pre>
    </div>
  ),
}));
vi.mock("../research/backtest/BacktestView", () => ({
  BacktestView: ({ meta, target }: { meta: TaskMetadata; target?: string }) => (
    <div
      className="embedded-backtest"
      data-task={meta.task_id}
      data-run={meta.run_id}
      data-target={target}
    />
  ),
}));
const chooseModel = async (name: string) => {
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".online-model-picker")!.click(),
  );
  await act(async () =>
    [...container.querySelectorAll<HTMLButtonElement>('[role="option"]')]
      .find((button) => button.textContent === name)!
      .click(),
  );
};
let root: Root;
let container: HTMLDivElement;
let parent: TaskMetadata;
let nodes: TaskNode[];
const openTask = vi.fn();
const render = async () =>
  act(async () =>
    root.render(
      <ComparePipeline
        parent={parent}
        nodes={nodes}
        target="http://selected-machine"
        onOpenTask={openTask}
        refreshedAt="2026-10-19T10:00:00Z"
      />,
    ),
  );
const click = (id: string) =>
  act(async () =>
    container
      .querySelector<HTMLButtonElement>(`[role="tab"][id$="-${id}-tab"]`)!
      .click(),
  );
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("en");
  const tasks = seed().tasks;
  parent = structuredClone(tasks.get("composite#playground_compare#demo")!);
  const seen = new Set<string>();
  nodes = [];
  const visit = (task: TaskMetadata) =>
    task.children.forEach((record) => {
      if (seen.has(record.run_id)) return;
      seen.add(record.run_id);
      const status = tasks.get(record.task_id!);
      nodes.push({
        record,
        status: status ? structuredClone(status) : null,
        error: "",
      });
      if (status) visit(status);
    });
  visit(parent);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  openTask.mockClear();
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

it.each(["en", "zh"])(
  "shows one navigation row and prioritizes differing checks in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    await render();
    expect(container.querySelectorAll('[role="tablist"]')).toHaveLength(1);
    expect(container.querySelectorAll('[role="tab"]')).toHaveLength(6);
    expect(container.querySelector("pre")?.dataset.run).toBe(parent.run_id);
    await click("results");
    expect(container.querySelectorAll(".operation-tab-connector")).toHaveLength(
      0,
    );
    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(4);
    expect(rows[0].textContent).toContain(i18n.t("nightly.checks.predictions"));
    expect(rows[0].textContent).toContain("pred: 2");
    expect(rows[0].textContent).toContain("1.200e-3");
    expect(container.textContent).not.toContain("[object Object]");
    await click("portfolio");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(5);
    expect(container.querySelector("tbody")?.textContent).toContain(
      i18n.t("nightly.checks.positions"),
    );
    await chooseModel("missing");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
    expect(container.textContent).not.toContain("pred: 2");
  },
);

it("shows a failure once, retains skipped stages and opens its exact child log", async () => {
  const error = "ValueError: Source training task failed";
  parent.state = "failed";
  parent.error = "Task exited with code 1";
  const step = parent.steps.find((s) => s.name === "nightly:etl")!;
  step.state = "failed";
  step.error = `ChildTaskError: Child Task 'history' failed: ${error}`;
  parent.steps
    .filter((s) => s.group === "nightly" && s !== step)
    .forEach((s) => {
      s.state = "skipped";
      s.error = "upstream_failed";
    });
  parent.output_params.models = {
    nightly: { status: "failed", error: step.error },
    missing: { status: "done" },
  };
  const history = nodes.find((n) => n.record.task.includes("history"))!;
  history.record.state = "failed";
  history.status!.state = "failed";
  history.status!.error = error;
  await render();
  await click("etl");
  expect(container.textContent?.split(error)).toHaveLength(2);
  expect(container.textContent).not.toContain("Task exited with code");
  expect(container.textContent).not.toContain("ChildTaskError");
  expect(container.querySelectorAll(".compare-stage-row")).toHaveLength(1);
  expect(container.querySelector(".pipeline-model")).toBeNull();
  expect(container.querySelector("pre")?.dataset.run).toBe(
    history.record.run_id,
  );
  expect(container.querySelector("pre")?.dataset.target).toBe(
    "http://selected-machine",
  );
  await click("prediction");
  expect(container.querySelector(".compare-stage-row")?.textContent).toContain(
    i18n.t("onlinePipeline.status.skipped"),
  );
  expect(container.querySelector("pre")).toBeNull();
});

it("keeps model logs isolated and refuses to substitute a replaced Run", async () => {
  await render();
  await click("etl");
  const select = container.querySelector<HTMLSelectElement>(
    ".pipeline-log-source select",
  )!;
  const nested = nodes.find((n) => n.record.task_id?.startsWith("etl#"))!;
  await act(async () => {
    select.value = `${nested.record.task_id}:${nested.record.run_id}`;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(container.querySelector("pre")?.dataset.run).toBe(
    nested.record.run_id,
  );
  nested.status = null;
  nested.error = "Run was replaced";
  await render();
  expect(container.querySelector("pre")).toBeNull();
  expect(container.querySelector('[role="alert"]')?.textContent).toBe(
    "Run was replaced",
  );
  const history = nodes.find((node) => node.record.task.includes("history"))!;
  await act(async () => {
    const available = container.querySelector<HTMLSelectElement>(
      ".pipeline-log-source select",
    )!;
    available.value = `${history.record.task_id}:${history.record.run_id}`;
    available.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(container.querySelector("pre")?.dataset.run).toBe(
    history.record.run_id,
  );
  await chooseModel("missing");
  expect(container.querySelector("pre")).toBeNull();
  expect(container.querySelectorAll("option")).toHaveLength(0);
  await click("logs");
  expect(container.querySelector("pre")?.dataset.run).toBe(parent.run_id);
});

it("resolves owned descendants and ignores an earlier attempt and similarly named models", () => {
  const old = structuredClone(
    parent.children.find((r) => r.node_name.includes("history"))!,
  );
  old.run_id = "old-run";
  parent.children.unshift(old);
  const unrelated = {
    ...old,
    node_name: "nightly-other-1445-a_stock_history",
    run_id: "unrelated",
  };
  parent.children.push(unrelated);
  nodes.unshift(
    { record: old, status: null, error: "old error" },
    { record: unrelated, status: null, error: "unrelated error" },
  );
  const model = compareModels(parent, nodes).find((m) => m.name === "nightly")!;
  expect(
    model.children.some((n) =>
      ["old-run", "unrelated"].includes(n.record.run_id),
    ),
  ).toBe(false);
  expect(model.children.some((n) => n.record.task_id?.startsWith("etl#"))).toBe(
    true,
  );
  expect(ownedCompareNodes([], nodes)).toHaveLength(0);
});

it("embeds the existing backtest report from the exact owned Run", async () => {
  const template = nodes[0];
  const task = structuredClone(template.status!);
  task.task_id = "backtest#nightly#report";
  task.run_id = "backtest-report-run";
  task.task_type = "backtest";
  task.output_params = { universes: { all: {} }, artifacts: {} };
  const record = {
    ...template.record,
    task: "a_stock_backtest",
    task_id: task.task_id,
    run_id: task.run_id,
    node_name: "nightly-a_stock_backtest",
  };
  parent.children.push(record);
  nodes.push({ record, status: task, error: "" });
  await render();
  await click("portfolio");
  const report = container.querySelector<HTMLElement>(".embedded-backtest")!;
  expect(report.dataset.task).toBe(task.task_id);
  expect(report.dataset.run).toBe(task.run_id);
  expect(report.dataset.target).toBe("http://selected-machine");
});

it("keeps shared download logs outside model stages", async () => {
  const template = nodes[0];
  const download = structuredClone(template.status!);
  download.task_id = "api#tushare_mins#nightly";
  download.run_id = "shared-download-run";
  download.task_type = "api";
  download.children = [];
  const record = {
    ...template.record,
    task: "tushare_mins",
    node_name: "tushare_mins",
    task_id: download.task_id,
    run_id: download.run_id,
  };
  parent.children.push(record);
  nodes.push({ record, status: download, error: "" });
  await render();
  await click("download");
  expect(container.querySelector("pre")?.dataset.run).toBe(download.run_id);
  await chooseModel("missing");
  expect(container.querySelector("pre")?.dataset.run).toBe(download.run_id);
  await click("prediction");
  expect(container.querySelector("pre")).toBeNull();
  await click("logs");
  expect(container.querySelector("pre")?.dataset.run).toBe(parent.run_id);
});
