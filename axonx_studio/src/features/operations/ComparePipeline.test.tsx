// @vitest-environment jsdom
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import type { TaskMetadata } from "../../shared/api/contracts";
import type { TaskNode } from "../tasks/tree";
import { ComparePipeline } from "./ComparePipeline";
import { compareModels, ownedCompareNodes } from "./compare";

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
      <pre data-task={task.task_id} data-target={target}>
        {task.task_id}
      </pre>
    </div>
  ),
}));
const chooseModel = async (name: string) => {
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".online-model-picker")!.click(),
  );
  await act(async () =>
    [...document.querySelectorAll<HTMLButtonElement>('[role="option"]')]
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
  parent = structuredClone(tasks.get("base#playground_compare#demo")!);
  const seen = new Set<string>();
  nodes = [];
  const visit = (task: TaskMetadata) =>
    task.children.forEach((record) => {
      if (seen.has(`${record.child_task_id}:${record.started_at}`)) return;
      seen.add(`${record.child_task_id}:${record.started_at}`);
      const status = tasks.get(record.child_task_id!);
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
    expect(container.querySelectorAll('[role="tab"]')).toHaveLength(5);
    expect(container.querySelector("pre")?.dataset.task).toBe(parent.task_id);
    await click("results");
    expect(container.querySelectorAll(".operation-tab-connector")).toHaveLength(
      0,
    );
    const checks = container.querySelectorAll(".comparison-check");
    expect(checks).toHaveLength(4);
    expect(checks[0].textContent).toContain(
      i18n.t("nightly.checks.predictions"),
    );
    expect(
      container.querySelector(".compare-diagnostics")?.hasAttribute("open"),
    ).toBe(true);
    expect(container.querySelector("pre")).toBeNull();
    expect(container.textContent).not.toContain("[object Object]");
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
  const history = nodes.find((n) => n.record.reg_name.includes("history"))!;
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
  expect(container.querySelector("pre")?.dataset.task).toBe(
    history.record.child_task_id,
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

it("keeps model logs isolated and refuses to substitute a restarted task", async () => {
  await render();
  await click("etl");
  expect(container.querySelector(".pipeline-log-source select")).toBeNull();
  expect(container.querySelector(".compare-active-model")).toBeNull();
  const nested = nodes.find((n) => n.record.child_task_id?.startsWith("etl#"))!;
  expect(container.querySelector("pre")?.dataset.task).toBe(
    nested.record.child_task_id,
  );
  nested.status = null;
  nested.error = "Task restarted";
  await render();
  expect(container.querySelector("pre")).toBeNull();
  expect(container.querySelector('[role="alert"]')?.textContent).toBe(
    "Task restarted",
  );
  await chooseModel("missing");
  expect(container.querySelector("pre")).toBeNull();
  expect(container.querySelectorAll("option")).toHaveLength(0);
  await click("logs");
  expect(container.querySelector("pre")?.dataset.task).toBe(parent.task_id);
});

it("resolves owned descendants and ignores an earlier attempt and similarly named models", () => {
  const old = structuredClone(
    parent.children.find((r) => r.node_name.includes("history"))!,
  );
  old.started_at = "2026-01-01T00:00:00Z";
  parent.children.unshift(old);
  const unrelated = {
    ...old,
    node_name: "nightly-other-1445-a_stock_history",
    started_at: "2026-01-16T00:00:00Z",
  };
  parent.children.push(unrelated);
  nodes.unshift(
    { record: old, status: null, error: "old error" },
    { record: unrelated, status: null, error: "unrelated error" },
  );
  const model = compareModels(parent, nodes).find((m) => m.name === "nightly")!;
  expect(
    model.children.some((n) =>
      ["2026-01-01T00:00:00Z", "2026-01-16T00:00:00Z"].includes(
        n.record.started_at || "",
      ),
    ),
  ).toBe(false);
  expect(
    model.children.some((n) => n.record.child_task_id?.startsWith("etl#")),
  ).toBe(true);
  expect(ownedCompareNodes([], nodes)).toHaveLength(0);
});

it("omits backtests even when an older comparison task contains one", async () => {
  window.location.hash = "#selected-machine/operations/comparison";
  const template = nodes[0];
  const task = structuredClone(template.status!);
  task.task_id = "backtest#nightly#report";
  task.started_at = "2026-01-05T00:00:00Z";
  task.task_type = "backtest";
  task.output_params = { universes: { all: {} }, artifacts: {} };
  const record = {
    ...template.record,
    reg_name: "a_stock_backtest",
    child_task_id: task.task_id,
    started_at: task.started_at,
    node_name: "nightly-a_stock_backtest",
  };
  parent.children.push(record);
  nodes.push({ record, status: task, error: "" });
  await render();
  expect(
    container.querySelector('[role="tab"][id$="-portfolio-tab"]'),
  ).toBeNull();
  expect(container.querySelector(".embedded-backtest")).toBeNull();
});

it("keeps shared download logs outside model stages", async () => {
  const template = nodes[0];
  const download = structuredClone(template.status!);
  download.task_id = "api#tushare_mins#nightly";
  download.started_at = "2026-01-06T00:00:00Z";
  download.task_type = "api";
  download.children = [];
  const record = {
    ...template.record,
    reg_name: "tushare_mins",
    node_name: "tushare_mins",
    child_task_id: download.task_id,
    started_at: download.started_at,
  };
  parent.children.push(record);
  nodes.push({ record, status: download, error: "" });
  await render();
  await click("download");
  expect(container.querySelector("pre")?.dataset.task).toBe(download.task_id);
  await chooseModel("missing");
  expect(container.querySelector("pre")?.dataset.task).toBe(download.task_id);
  await click("prediction");
  expect(container.querySelector("pre")).toBeNull();
  await click("logs");
  expect(container.querySelector("pre")?.dataset.task).toBe(parent.task_id);
});
