// @vitest-environment jsdom
import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { taskStatus } from "../../playground/fixtures";
import { getTaskStatus } from "./api";
import { TaskDetailPage } from "./TaskDetailPage";

vi.mock("./api", () => ({ getTaskStatus: vi.fn(), cancelTask: vi.fn() }));
vi.mock("./TaskLogPanel", () => ({
  TaskLogPanel: () => <div>log viewer</div>,
}));
vi.mock("./TaskSteps", () => ({ TaskSteps: () => null }));
vi.mock("../online/QualityReport", () => ({ TaskQuality: () => null }));
vi.mock("../task-graph/TaskGraphPage", () => ({
  TaskGraphPanel: () => <div>task graph</div>,
}));

afterEach(() => {
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

it("keeps loading after StrictMode aborts the first request, then switches all four tabs", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("zh");
  const task = taskStatus("base", "base#demo", "demo");
  let resolve!: (value: typeof task) => void;
  const pending = new Promise<typeof task>((done) => {
    resolve = done;
  });
  vi.mocked(getTaskStatus).mockImplementation((_id, _target, signal) => {
    if (vi.mocked(getTaskStatus).mock.calls.length === 1) {
      return new Promise((_resolve, reject) => {
        signal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    }
    return pending;
  });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <StrictMode>
          <TaskDetailPage
            taskId={task.task_id}
            target="remote"
            onBack={vi.fn()}
            onOpenTask={vi.fn()}
            onInterpretTask={vi.fn()}
            onOpenResearch={vi.fn()}
            onConnection={vi.fn()}
          />
        </StrictMode>,
      ),
    );
    expect(getTaskStatus).toHaveBeenCalledTimes(2);
    expect(container.querySelector(".task-detail-loading")).not.toBeNull();
    expect(container.querySelector(".error-banner")).toBeNull();
    await act(async () => resolve(task));
    const tabs = [
      ...container.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    ];
    expect(tabs).toHaveLength(4);
    expect(tabs[2].getAttribute("aria-selected")).toBe("true");
    for (const tab of tabs) {
      expect(tab.querySelector("svg, .task-orb")).not.toBeNull();
      await act(async () => tab.click());
      expect(
        container.querySelectorAll('[role="tabpanel"]:not([hidden])'),
      ).toHaveLength(1);
      expect(tab.getAttribute("aria-selected")).toBe("true");
    }
    await act(async () => tabs[0].click());
    expect(container.querySelector(".task-log-card")).not.toBeNull();
    expect(container.querySelector(".task-relations-card")).not.toBeNull();
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }
});
