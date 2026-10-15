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
