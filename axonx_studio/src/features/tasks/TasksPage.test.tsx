// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TasksPage } from "./TasksPage";
import { listTaskStatuses } from "./api";
import type { TaskSummary } from "./types";
vi.mock("./api", () => ({
  listTaskStatuses: vi.fn(),
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string, options?: { returnObjects?: boolean }) =>
      options?.returnObjects ? {} : key,
  }),
}));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
function task(
  taskId: string,
  state: TaskSummary["state"] = "running",
): TaskSummary {
  return {
    parent_task_id: null,
    display_name: taskId,
    is_replica: false,
    is_online: false,
    step_progress: null,
    category: null,
    report_kind: null,
    task_id: taskId,
    task_type: "train",
    reg_name: taskId.split("#")[1],
    source: { kind: "exec" },
    state,
    pid: 1234,
    machine_id: "playground",
    execution_target: null,
    workspace_dir: null,
    process_started_at: "2026-01-01T00:00:00Z",
    created_at: null,
    started_at: "2026-10-26T00:00:00Z",
    finished_at: null,
    error: "",
    exit_code: 0,
    log_path: "",
  };
}
async function selectState(value: string) {
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>(
        '[role="combobox"][aria-label="state"]',
      )!
      .click(),
  );
  const option = [
    ...document.querySelectorAll<HTMLButtonElement>('[role="option"]'),
  ].find((option) =>
    option.textContent?.startsWith(value ? `states.${value}` : "allStates"),
  )!;
  await act(async () => option.click());
}
let root: Root;
let container: HTMLDivElement;
const onConnection = vi.fn();
const onOpenTask = vi.fn();
async function render(target = "machine-a") {
  await act(async () => {
    root.render(
      <TasksPage
        target={target}
        onOpenTask={onOpenTask}
        onConnection={onConnection}
      />,
    );
  });
}
async function click(selector: string) {
  const element = container.querySelector<HTMLElement>(selector);
  expect(element).not.toBeNull();
  await act(async () => {
    element!.click();
  });
}
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.useFakeTimers();
  vi.resetAllMocks();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(listTaskStatuses).mockResolvedValue([task("train#demo#a")]);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("task request ownership", () => {
  it("deduplicates manual refresh while a list request is pending", async () => {
    const pending = deferred<TaskSummary[]>();
    vi.mocked(listTaskStatuses).mockReturnValue(pending.promise);
    await render();
    await click('[aria-label="refreshNow"]');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(listTaskStatuses).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve([]));
  });
});

describe("grouped task list", () => {
  async function openGroupMenu(key = "train#demo") {
    await act(async () => {
      container
        .querySelector(`[aria-label="${key}"]`)!
        .dispatchEvent(new MouseEvent("contextmenu", { bubbles: true }));
    });
  }

  it("disables group actions for active-only groups and closes on Escape", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#running"),
      task("train#demo#second", "running"),
    ]);
    await render();
    await openGroupMenu();
    expect(
      [
        ...container.querySelectorAll<HTMLButtonElement>('[role="menuitem"]'),
      ].every((button) => button.disabled),
    ).toBe(true);
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(container.querySelector('[role="menu"]')).toBeNull();
  });

  it("collapses terminal groups and opens the complete task identity", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#first", "succeeded"),
      task("train#demo#second", "failed"),
    ]);
    await render();
    expect(container.querySelectorAll(".task-group")).toHaveLength(1);
    expect(container.querySelector("tbody")).toBeNull();
    await click(".task-group-toggle");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(container.querySelector("tbody strong")!.textContent).toBe("first");
    await click("tbody tr");
    expect(onOpenTask).toHaveBeenCalledWith("train#demo#first");
  });

  it("keeps collapsed active groups and page positions across polling", async () => {
    const records = Array.from({ length: 101 }, (_, index) =>
      task(`train#demo#run-${String(index).padStart(3, "0")}`),
    );
    vi.mocked(listTaskStatuses).mockResolvedValue(records);
    await render();
    expect(container.querySelectorAll("tbody tr")).toHaveLength(50);
    await click('[aria-label="taskGroups.next"]');
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "run-050",
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "run-050",
    );
    await click(".task-group-toggle");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(container.querySelector("tbody")).toBeNull();
    await click(".task-group-toggle");
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "run-050",
    );
    await selectState("running");
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "run-000",
    );
  });

  it("resets group expansion and pagination when switching machines", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#done", "succeeded"),
    ]);
    await render();
    await click(".task-group-toggle");
    await render("machine-b");
    expect(container.querySelector("tbody")).toBeNull();
  });

  it("shows the full identity when a demo task has no name segment and copies without opening", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo", "succeeded"),
    ]);
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await render();
    await click(".task-group-toggle");
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "train#demo",
    );
    await click('[aria-label="copyTaskId"]');
    expect(writeText).toHaveBeenCalledWith("train#demo");
    expect(onOpenTask).not.toHaveBeenCalled();
  });
});

it.each(["running", "succeeded"] as const)(
  "shows %s independent exec Tasks in their ordinary group",
  async (state) => {
    const scheduled = task("train#demo#old", state);
    vi.mocked(listTaskStatuses).mockResolvedValue([scheduled]);
    await render();
    expect(container.querySelectorAll(".task-group")).toHaveLength(1);
    if (state === "succeeded") await click(".task-group-toggle");
    await click("tbody tr");
    expect(onOpenTask).toHaveBeenCalledWith(scheduled.task_id);
  },
);
