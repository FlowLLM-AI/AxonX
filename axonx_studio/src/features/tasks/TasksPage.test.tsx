// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TasksPage } from "./TasksPage";
import { cancelTask, deleteTasks, listTaskStatuses } from "./api";
import type { TaskStatus } from "./types";
vi.mock("./api", () => ({
  listTaskStatuses: vi.fn(),
  cancelTask: vi.fn(),
  deleteTasks: vi.fn(),
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
  state: TaskStatus["state"] = "running",
): TaskStatus {
  return {
    task_id: taskId,
    run_id: taskId,
    task_type: "train",
    task_name: taskId,
    config: {},
    state,
    pid: null,
    created_at: null,
    started_at: null,
    finished_at: null,
    steps: [],
    result: {},
    error: "",
    exit_code: 0,
    log_path: "",
  };
}
let root: Root;
let container: HTMLDivElement;
const onConnection = vi.fn();
async function render(target = "machine-a") {
  await act(async () => {
    root.render(
      <TasksPage
        target={target}
        onSubmit={() => {}}
        onOpenTask={() => {}}
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
async function openMenu() {
  await act(async () => {
    container
      .querySelector("tbody tr")!
      .dispatchEvent(new MouseEvent("contextmenu", { bubbles: true }));
  });
}
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.useFakeTimers();
  vi.resetAllMocks();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(listTaskStatuses).mockResolvedValue([task("train#a")]);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("task request ownership", () => {
  it("deduplicates manual refresh while a list request is pending", async () => {
    const pending = deferred<TaskStatus[]>();
    vi.mocked(listTaskStatuses).mockReturnValue(pending.promise);
    await render();
    await click('[aria-label="refreshNow"]');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(listTaskStatuses).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve([]));
  });
  it("invalidates an older list after cancellation and ignores its late response", async () => {
    await render();
    const pending = deferred<TaskStatus[]>();
    vi.mocked(listTaskStatuses).mockReturnValueOnce(pending.promise);
    await click('[aria-label="refreshNow"]');
    const signal = vi.mocked(listTaskStatuses).mock.calls[1][1]!;
    vi.mocked(cancelTask).mockResolvedValue(true);
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#fresh", "cancelled"),
    ]);
    await openMenu();
    await click('[role="menuitem"].danger');
    await click('[role="dialog"] .danger-button');
    expect(signal.aborted).toBe(true);
    await act(async () => pending.resolve([task("train#stale")]));
    expect(container.textContent).toContain("train#fresh");
    expect(container.textContent).not.toContain("train#stale");
  });
  it.each(["success", "failure"])(
    "ignores cancellation %s after switching machines",
    async (outcome) => {
      await render();
      const cancellation = deferred<boolean>();
      vi.mocked(cancelTask).mockReturnValue(cancellation.promise);
      await openMenu();
      await click('[role="menuitem"].danger');
      await click('[role="dialog"] .danger-button');
      const nextList = deferred<TaskStatus[]>();
      vi.mocked(listTaskStatuses).mockReturnValue(nextList.promise);
      await render("machine-b");
      const nextSignal = vi.mocked(listTaskStatuses).mock.calls[1][1]!;
      await act(async () => {
        if (outcome === "success") cancellation.resolve(true);
        else cancellation.reject(new Error("old machine failure"));
      });
      expect(nextSignal.aborted).toBe(false);
      expect(listTaskStatuses).toHaveBeenCalledTimes(2);
      expect(container.textContent).not.toContain("old machine failure");
      await act(async () => nextList.resolve([task("train#b")]));
      expect(container.textContent).toContain("train#b");
      expect(container.querySelector('[role="dialog"]')).toBeNull();
    },
  );
  it.each(["success", "failure"])(
    "ignores deletion %s after switching machines",
    async (outcome) => {
      vi.mocked(listTaskStatuses).mockResolvedValue([
        task("train#a", "succeeded"),
      ]);
      await render();
      const deletion = deferred<string[]>();
      vi.mocked(deleteTasks).mockReturnValue(deletion.promise);
      await openMenu();
      await click('[role="menuitem"]:nth-of-type(2)');
      await click(".task-selection-actions .danger-outline");
      await click('[role="dialog"] .danger-button');
      const nextList = deferred<TaskStatus[]>();
      vi.mocked(listTaskStatuses).mockReturnValue(nextList.promise);
      await render("machine-b");
      const nextSignal = vi.mocked(listTaskStatuses).mock.calls[1][1]!;
      await act(async () => {
        if (outcome === "success") deletion.resolve(["train#a"]);
        else deletion.reject(new Error("old machine failure"));
      });
      expect(nextSignal.aborted).toBe(false);
      expect(listTaskStatuses).toHaveBeenCalledTimes(2);
      expect(container.textContent).not.toContain("old machine failure");
      expect(container.querySelector('[role="dialog"]')).toBeNull();
      expect(container.querySelector(".task-selection-actions")).toBeNull();
      await act(async () => nextList.resolve([task("train#b")]));
      expect(container.textContent).toContain("train#b");
    },
  );
  it("does not launch a new list when deletion finishes after leaving the page", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#a", "succeeded"),
    ]);
    await render();
    const deletion = deferred<string[]>();
    vi.mocked(deleteTasks).mockReturnValue(deletion.promise);
    await openMenu();
    await click('[role="menuitem"]:nth-of-type(2)');
    await click(".task-selection-actions .danger-outline");
    await click('[role="dialog"] .danger-button');
    await act(async () => root.render(null));
    await act(async () => deletion.resolve(["train#a"]));
    expect(listTaskStatuses).toHaveBeenCalledTimes(1);
  });
});
