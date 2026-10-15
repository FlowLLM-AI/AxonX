// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TasksPage } from "./TasksPage";
import {
  cancelTask,
  deleteTasks,
  listTaskStatuses,
  listSchedules,
} from "./api";
import type { TaskSummary } from "./types";
vi.mock("./api", () => ({
  listTaskStatuses: vi.fn(),
  listSchedules: vi.fn(),
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
  state: TaskSummary["state"] = "running",
): TaskSummary {
  return {
    display_name: taskId,
    is_replica: false,
    is_online: false,
    step_progress: null,
    report_kind: null,
    task_id: taskId,
    run_id: `run-${taskId}`,
    task_type: "train",
    reg_name: taskId.split("#")[1],
    source: { kind: "submit", schedule: null },
    state,
    pid: null,
    created_at: null,
    started_at: null,
    finished_at: null,
    error: "",
    exit_code: 0,
    log_path: "",
  };
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
        onSubmit={() => {}}
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
async function openMenu() {
  if (!container.querySelector("tbody tr")) await click(".task-group-toggle");
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
  vi.mocked(listSchedules).mockResolvedValue([]);
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
  it("invalidates an older list after cancellation and ignores its late response", async () => {
    await render();
    const pending = deferred<TaskSummary[]>();
    vi.mocked(listTaskStatuses).mockReturnValueOnce(pending.promise);
    await click('[aria-label="refreshNow"]');
    const signal = vi.mocked(listTaskStatuses).mock.calls[1][1]!;
    vi.mocked(cancelTask).mockResolvedValue(true);
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#fresh", "cancelled"),
    ]);
    await openMenu();
    await click('[role="menuitem"].danger');
    await click('[role="dialog"] .danger-button');
    expect(cancelTask).toHaveBeenCalledWith("run-train#demo#a", "machine-a");
    expect(signal.aborted).toBe(true);
    await act(async () => pending.resolve([task("train#demo#stale")]));
    expect(
      container.querySelector('strong[title="train#demo#fresh"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('strong[title="train#demo#stale"]'),
    ).toBeNull();
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
      const nextList = deferred<TaskSummary[]>();
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
      await act(async () => nextList.resolve([task("train#demo#b")]));
      expect(
        container.querySelector('strong[title="train#demo#b"]'),
      ).not.toBeNull();
      expect(container.querySelector('[role="dialog"]')).toBeNull();
    },
  );
  it.each(["success", "failure"])(
    "ignores deletion %s after switching machines",
    async (outcome) => {
      vi.mocked(listTaskStatuses).mockResolvedValue([
        task("train#demo#a", "succeeded"),
      ]);
      await render();
      const deletion = deferred<string[]>();
      vi.mocked(deleteTasks).mockReturnValue(deletion.promise);
      await openMenu();
      await click('[role="menuitem"]:nth-of-type(2)');
      await click(".task-selection-actions .danger-outline");
      await click('[role="dialog"] .danger-button');
      const nextList = deferred<TaskSummary[]>();
      vi.mocked(listTaskStatuses).mockReturnValue(nextList.promise);
      await render("machine-b");
      const nextSignal = vi.mocked(listTaskStatuses).mock.calls[1][1]!;
      await act(async () => {
        if (outcome === "success") deletion.resolve(["train#demo#a"]);
        else deletion.reject(new Error("old machine failure"));
      });
      expect(nextSignal.aborted).toBe(false);
      expect(listTaskStatuses).toHaveBeenCalledTimes(2);
      expect(container.textContent).not.toContain("old machine failure");
      expect(container.querySelector('[role="dialog"]')).toBeNull();
      expect(container.querySelector(".task-selection-actions")).toBeNull();
      await act(async () => nextList.resolve([task("train#demo#b")]));
      expect(
        container.querySelector('strong[title="train#demo#b"]'),
      ).not.toBeNull();
    },
  );
  it("does not launch a new list when deletion finishes after leaving the page", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#a", "succeeded"),
    ]);
    await render();
    const deletion = deferred<string[]>();
    vi.mocked(deleteTasks).mockReturnValue(deletion.promise);
    await openMenu();
    await click('[role="menuitem"]:nth-of-type(2)');
    await click(".task-selection-actions .danger-outline");
    await click('[role="dialog"] .danger-button');
    await act(async () => root.render(null));
    await act(async () => deletion.resolve(["train#demo#a"]));
    expect(listTaskStatuses).toHaveBeenCalledTimes(1);
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

  it("right-click selects terminal tasks across pages without expanding the group", async () => {
    const records = Array.from({ length: 51 }, (_, index) =>
      task(`train#demo#run-${index}`, "succeeded"),
    );
    vi.mocked(listTaskStatuses).mockResolvedValue(records);
    await render();
    await openGroupMenu();
    expect(container.querySelector("tbody")).toBeNull();
    await click('[role="menuitem"]:not(.danger)');
    expect(container.querySelector('[role="menu"]')).toBeNull();
    expect(
      container.querySelector<HTMLInputElement>(".task-group-header input")!
        .checked,
    ).toBe(true);
    await click(".task-selection-actions .danger-outline");
    vi.mocked(deleteTasks).mockResolvedValue(
      records.map((item) => item.task_id),
    );
    await click('[role="dialog"] .danger-button');
    expect(vi.mocked(deleteTasks).mock.calls[0][0]).toHaveLength(51);
  });

  it("group deletion confirms only matching terminal tasks and preserves other selections", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#other#keep", "succeeded"),
      task("train#demo#good", "succeeded"),
      task("train#demo#bad", "failed"),
      task("train#demo#active"),
    ]);
    await render();
    await openGroupMenu("train#other");
    await click('[role="menuitem"]:not(.danger)');
    await act(async () => {
      const select = container.querySelector<HTMLSelectElement>(
        '[aria-label="state"]',
      )!;
      select.value = "failed";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await openGroupMenu();
    await click('[role="menuitem"].danger');
    expect(deleteTasks).not.toHaveBeenCalled();
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    vi.mocked(deleteTasks).mockResolvedValue(["train#demo#bad"]);
    await click('[role="dialog"] .danger-button');
    expect(deleteTasks).toHaveBeenCalledWith(["train#demo#bad"], "machine-a");
    expect(container.querySelector(".task-selection-actions")).not.toBeNull();
    await act(async () => {
      const select = container.querySelector<HTMLSelectElement>(
        '[aria-label="state"]',
      )!;
      select.value = "";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(
      container
        .querySelector<HTMLInputElement>('[aria-label="train#other"]')!
        .parentElement!.querySelector<HTMLInputElement>("input")!.checked,
    ).toBe(true);
  });

  it("disables group actions for active-only groups and closes on Escape", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#running"),
      task("train#demo#queued", "queued"),
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

  it("does not delete a task that became active while group confirmation was open", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#done", "succeeded"),
    ]);
    await render();
    await openGroupMenu();
    await click('[role="menuitem"].danger');
    vi.mocked(listTaskStatuses).mockResolvedValue([task("train#demo#done")]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(
      container.querySelector<HTMLButtonElement>(
        '[role="dialog"] .danger-button',
      )!.disabled,
    ).toBe(true);
    await click('[role="dialog"] .danger-button');
    expect(deleteTasks).not.toHaveBeenCalled();
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
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "run-050",
    );
    await click(".task-group-toggle");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(container.querySelector("tbody")).toBeNull();
    await click(".task-group-toggle");
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "run-050",
    );
    await act(async () => {
      const select = container.querySelector<HTMLSelectElement>(
        '[aria-label="state"]',
      )!;
      select.value = "running";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.querySelector("tbody strong")!.textContent).toBe(
      "run-000",
    );
  });

  it("selects terminal members across pages and shows a partial group selection", async () => {
    const records = Array.from({ length: 51 }, (_, index) =>
      task(`train#demo#run-${index}`, "succeeded"),
    );
    records.push(task("train#demo#active"));
    vi.mocked(listTaskStatuses).mockResolvedValue(records);
    await render();
    await click('[aria-label="enableMultiSelect"]');
    const group = container.querySelector<HTMLInputElement>(
      ".task-group-header input",
    )!;
    await click("tbody input:not(:disabled)");
    expect(group.indeterminate).toBe(true);
    await act(async () => group.click());
    expect(group.checked).toBe(true);
    await click(".task-selection-actions .danger-outline");
    vi.mocked(deleteTasks).mockResolvedValue(
      records
        .filter((item) => item.state !== "running")
        .map((item) => item.task_id),
    );
    await click('[role="dialog"] .danger-button');
    expect(vi.mocked(deleteTasks).mock.calls[0][0]).toHaveLength(51);
    expect(vi.mocked(deleteTasks).mock.calls[0][0]).not.toContain(
      "train#demo#active",
    );
  });

  it("group selection includes only filtered terminal task identities", async () => {
    vi.mocked(listTaskStatuses).mockResolvedValue([
      task("train#demo#good", "succeeded"),
      task("train#demo#bad", "failed"),
      task("train#demo#active"),
    ]);
    await render();
    await act(async () => {
      const select = container.querySelector<HTMLSelectElement>(
        '[aria-label="state"]',
      )!;
      select.value = "failed";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
    await click('[aria-label="enableMultiSelect"]');
    await click(".task-group-header input");
    await click(".task-selection-actions .danger-outline");
    vi.mocked(deleteTasks).mockResolvedValue(["train#demo#bad"]);
    await click('[role="dialog"] .danger-button');
    expect(deleteTasks).toHaveBeenCalledWith(["train#demo#bad"], "machine-a");
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

  it("filter-wide selection includes collapsed groups and excludes active tasks", async () => {
    const records = [
      task("train#first#done", "succeeded"),
      task("train#second#failed", "failed"),
      task("train#second#active"),
    ];
    vi.mocked(listTaskStatuses).mockResolvedValue(records);
    await render();
    await click('[aria-label="enableMultiSelect"]');
    await click('[aria-label="taskGroups.selectFiltered"]');
    expect(
      container.querySelector<HTMLInputElement>("tbody input:disabled")!
        .checked,
    ).toBe(false);
    await click(".task-selection-actions .danger-outline");
    vi.mocked(deleteTasks).mockResolvedValue(
      records.slice(0, 2).map((item) => item.task_id),
    );
    await click('[role="dialog"] .danger-button');
    expect(deleteTasks).toHaveBeenCalledWith(
      ["train#second#failed", "train#first#done"],
      "machine-a",
    );
  });
});

it("separates schedule Tasks and lists schedules without Tasks", async () => {
  const scheduled = task("train#demo#scheduled");
  scheduled.source.schedule = {
    name: "daily",
    job: "submit",
    trigger_id: "trigger",
    triggered_at: "2026-10-13T01:00:00Z",
  };
  vi.mocked(listTaskStatuses).mockResolvedValue([
    scheduled,
    task("train#demo#manual", "succeeded"),
  ]);
  const schedule = (name: string, job: string) => ({
    name,
    job,
    description: `Description for ${name}`,
    cron: "0 9 * * *",
    timezone: "Asia/Shanghai",
    arguments: {},
    concurrency_policy: "forbid" as const,
    next_run_at: "2026-10-14T01:00:00Z",
    running: 0,
    last_trigger: null,
  });
  vi.mocked(listSchedules).mockResolvedValue([
    schedule("daily", "submit"),
    schedule("sync", "sync_flush"),
  ]);
  await render();
  expect(container.textContent).not.toContain("sync_flush");
  await click('[role="tab"]');
  expect(
    container.querySelector('[role="tab"]')?.getAttribute("aria-selected"),
  ).toBe("true");
  expect(container.textContent).toContain("sync_flush");
  expect(container.textContent).toContain("Asia/Shanghai");
  expect(container.textContent).toContain("schedules.noActiveTasks");
  expect(container.textContent).toContain("Description for daily");
  expect(container.textContent).toContain("scheduled");
  expect(container.textContent).not.toContain("manual");
  await click("tbody tr");
  expect(onOpenTask).toHaveBeenCalledWith(scheduled.task_id);
  expect(vi.mocked(listSchedules).mock.calls[0][0]).toBe("machine-a");
});

it.each(["running", "succeeded"] as const)(
  "retains %s schedule Tasks after configuration removal",
  async (state) => {
    const scheduled = task("train#demo#old", state);
    scheduled.source.schedule = {
      name: "removed",
      job: "submit",
      trigger_id: "trigger",
      triggered_at: "2026-10-13T01:00:00Z",
    };
    vi.mocked(listTaskStatuses).mockResolvedValue([scheduled]);
    await render();
    await click('[role="tab"]');
    expect(container.textContent).toContain("schedules.removed");
    expect(container.querySelectorAll(".schedule-card")).toHaveLength(1);
    expect(container.querySelectorAll(".task-group")).toHaveLength(1);
    if (state === "succeeded") {
      await click(".task-group-toggle");
      await click(".schedule-history > summary");
    }
    expect(container.querySelector("tbody tr")).not.toBeNull();
  },
);

it("keeps active tasks visible and isolates finished group actions within a schedule", async () => {
  const active = task("train#demo#active");
  const finished = task("train#demo#finished", "succeeded");
  for (const item of [active, finished]) {
    item.source.schedule = {
      name: "daily",
      job: "submit",
      trigger_id: "trigger",
      triggered_at: "2026-10-13T01:00:00Z",
    };
  }
  vi.mocked(listTaskStatuses).mockResolvedValue([active, finished]);
  await render();
  await click('[role="tab"]');
  expect(container.querySelectorAll(".task-group")).toHaveLength(1);
  expect(
    container.querySelectorAll(".task-group > .task-group-members tbody tr"),
  ).toHaveLength(1);
  expect(container.querySelector("tbody")?.textContent).toContain("active");
  expect(
    container.querySelector<HTMLDetailsElement>(".schedule-history")?.open,
  ).toBe(false);
  await click(".schedule-history > summary");
  await act(async () =>
    container
      .querySelector(".schedule-card .task-group-header")!
      .dispatchEvent(new MouseEvent("contextmenu", { bubbles: true })),
  );
  await click('[role="menuitem"].danger');
  vi.mocked(deleteTasks).mockResolvedValue([finished.task_id]);
  await click('[role="dialog"] .danger-button');
  expect(deleteTasks).toHaveBeenCalledWith([finished.task_id], "machine-a");
});

it("reports schedule loading failures and never mixes records from another target", async () => {
  vi.mocked(listSchedules).mockRejectedValueOnce(
    new Error("Schedules unavailable"),
  );
  await render();
  expect(container.textContent).toContain("Schedules unavailable");
  expect(onConnection).toHaveBeenLastCalledWith(false);
  await render("machine-b");
  expect(container.textContent).not.toContain("Schedules unavailable");
  expect(vi.mocked(listSchedules).mock.calls.at(-1)?.[0]).toBe("machine-b");
});

it("uses schedule-specific empty state and supports keyboard tab navigation", async () => {
  vi.mocked(listTaskStatuses).mockResolvedValue([]);
  await render();
  const other = container.querySelector<HTMLButtonElement>("#tasks-tab-other")!;
  expect(other.tabIndex).toBe(0);
  await act(async () =>
    other.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Home", bubbles: true }),
    ),
  );
  const scheduled = container.querySelector<HTMLButtonElement>(
    "#tasks-tab-scheduled",
  )!;
  expect(scheduled.tabIndex).toBe(0);
  expect(document.activeElement).toBe(scheduled);
  expect(container.textContent).toContain("schedules.emptyTitle");
  expect(container.textContent).toContain("schedules.emptyHint");
});
