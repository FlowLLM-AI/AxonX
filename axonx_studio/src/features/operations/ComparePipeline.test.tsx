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
    expect(container.querySelectorAll('[role="tab"]')).toHaveLength(6);
    expect(container.querySelector("pre")?.dataset.task).toBe(parent.task_id);
    await click("results");
    expect(container.querySelectorAll(".operation-tab-connector")).toHaveLength(
      0,
    );
    const checks = container.querySelectorAll(".comparison-check");
    expect(checks).toHaveLength(9);
    expect(checks[0].textContent).toContain(
      i18n.t("nightly.checks.predictions"),
    );
    expect(
      container.querySelector(".compare-diagnostics")?.hasAttribute("open"),
    ).toBe(true);
    expect(container.querySelector("pre")).toBeNull();
    expect(container.textContent).not.toContain("[object Object]");
    await chooseModel("missing · 14:45");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
    expect(container.textContent).not.toContain("pred: 2");
  },
);

it("shows a failure once, retains skipped stages and opens its exact child log", async () => {
  const error = "ValueError: Source training task failed";
  parent.state = "failed";
  parent.error = "Task exited with code 1";
  const step = parent.steps.find((s) => s.name === "nightly-1445:etl")!;
  step.state = "failed";
  step.error = `ChildTaskError: Child Task 'history' failed: ${error}`;
  parent.steps
    .filter((s) => s.group === "nightly-1445" && s !== step)
    .forEach((s) => {
      s.state = "skipped";
      s.error = "upstream_failed";
    });
  parent.output_params.models = {
    "1445": {
      nightly: { status: "failed", error: step.error },
      missing: { status: "done" },
    },
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

it.each(["en", "zh"])(
  "keeps a successful comparison's ledger differences visible in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    parent.state = "succeeded";
    parent.error = "";
    const report = nodes.find((node) =>
      Array.isArray(node.status?.output_params.comparisons),
    )!.status!;
    report.state = "succeeded";
    report.error = "";
    report.output_params.comparisons = [
      {
        key: "20260115/1445",
        status: "different",
        metrics: {
          stages: {
            predictions: { consistent: true },
            daily: {
              consistent: false,
              offline_rows: 1,
              online_rows: 1,
              mismatches: { top30_holdings: 1 },
            },
          },
        },
      },
    ];
    await render();
    await click("results");
    const checks = container.querySelectorAll(".comparison-check");
    expect(checks).toHaveLength(2);
    expect(checks[0].textContent).toContain(i18n.t("nightly.checks.daily"));
    expect(checks[0].textContent).toContain("top30_holdings");
    expect(checks[0].classList.contains("state-different")).toBe(true);
    expect(checks[1].classList.contains("state-consistent")).toBe(true);
    expect(container.querySelector(".online-warning")).toBeNull();
  },
);

it("prefers the parent's archived comparison and keeps it after children disappear", async () => {
  const outcomes = parent.output_params.models as Record<
    string,
    Record<string, Record<string, unknown>>
  >;
  outcomes["1445"].nightly.comparison = {
    key: "20260105/1445",
    status: "consistent",
    artifacts: {},
    metrics: {
      stages: { predictions: { consistent: true, mismatches: { pred: 0 } } },
    },
  };
  await render();
  await chooseModel("nightly · 14:45");
  await click("results");
  expect(container.querySelectorAll(".comparison-check")).toHaveLength(1);
  expect(
    container
      .querySelector(".comparison-check")
      ?.classList.contains("state-consistent"),
  ).toBe(true);
  nodes = [];
  await render();
  expect(container.querySelectorAll(".comparison-check")).toHaveLength(1);
  expect(
    container
      .querySelector(".comparison-check")
      ?.classList.contains("state-consistent"),
  ).toBe(true);
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
  await chooseModel("missing · 14:45");
  expect(container.querySelector("pre")).toBeNull();
  expect(container.querySelectorAll("option")).toHaveLength(0);
  await click("logs");
  expect(container.querySelector("pre")?.dataset.task).toBe(parent.task_id);
});

it("resolves owned descendants and ignores an earlier attempt and similarly named models", () => {
  const old = structuredClone(
    parent.children.find((r) => r.node_name.endsWith("-a_stock_history"))!,
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
  const model = compareModels(parent, nodes).find(
    (m) => m.name === "nightly-1445",
  )!;
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

it("shows registered portfolio logs through their semantic stage", async () => {
  const schedule = parent.input_params.models as Record<
    string,
    Record<string, unknown>[]
  >;
  schedule["1445"][0].portfolio = { reg_name: "custom_construction" };
  const template = nodes[0];
  const task = structuredClone(template.status!);
  task.task_id = "portfolio#custom_construction#nightly";
  task.task_type = "portfolio";
  task.children = [];
  const record = {
    ...template.record,
    reg_name: "custom_construction",
    child_task_id: task.task_id,
    node_name: "nightly-1445-custom_construction",
  };
  parent.children.push(record);
  nodes.push({ record, status: task, error: "" });
  await render();
  await click("portfolio");
  expect(container.querySelector("pre")?.dataset.task).toBe(task.task_id);
});

it("finds comparison output through its declared custom registration", async () => {
  const schedule = parent.input_params.models as Record<
    string,
    Record<string, unknown>[]
  >;
  schedule["1445"][0].compare = { reg_name: "custom_audit" };
  const node = nodes.find((item) =>
    Array.isArray(item.status?.output_params.comparisons),
  )!;
  node.record.reg_name = "custom_audit";
  node.record.node_name = "nightly-1445-custom_audit";
  node.record.child_task_id = "analysis#custom_audit#nightly";
  node.status!.task_id = node.record.child_task_id;
  await render();
  await click("results");
  expect(container.querySelectorAll(".comparison-check")).toHaveLength(9);
});

it("keeps the same model isolated across signal times", () => {
  parent.input_params.models = {
    "1445": [{ task_name: "same", train: { reg_name: "a_stock_train" } }],
    "0945": [{ task_name: "same", train: { reg_name: "a_stock_train" } }],
  };
  parent.output_params.models = {
    "0945": { same: { status: "failed", error: "morning failed" } },
    "1445": { same: { status: "done" } },
  };
  parent.children = [];
  parent.steps = [];
  const models = compareModels(parent, []);
  expect(models.map((model) => model.name)).toEqual(["same-0945", "same-1445"]);
  expect(models.map((model) => model.label)).toEqual([
    "same · 09:45",
    "same · 14:45",
  ]);
  expect(models.map((model) => model.state)).toEqual(["failed", "done"]);
  expect(models[1].outcome.error).toBeUndefined();
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
  await chooseModel("missing · 14:45");
  expect(container.querySelector("pre")?.dataset.task).toBe(download.task_id);
  await click("prediction");
  expect(container.querySelector("pre")).toBeNull();
  await click("logs");
  expect(container.querySelector("pre")?.dataset.task).toBe(parent.task_id);
});
