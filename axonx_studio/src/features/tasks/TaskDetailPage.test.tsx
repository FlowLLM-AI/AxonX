// @vitest-environment jsdom
import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { taskStatus } from "../../playground/fixtures";
import { cancelTask, getTaskStatus } from "./api";
import { TaskDetailPage } from "./TaskDetailPage";

vi.mock("./api", () => ({ getTaskStatus: vi.fn(), cancelTask: vi.fn() }));
vi.mock("./TaskLogPanel", () => ({
  TaskLogPanel: () => <div>log viewer</div>,
}));
vi.mock("../task-graph/TaskGraphPage", () => ({
  TaskGraphPanel: () => <div>task graph</div>,
}));

afterEach(() => {
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

it.each(["task", "machine", "cancellation"] as const)(
  "discards the previous selection and late %s responses",
  async (change) => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await i18n.changeLanguage("en");
    const previous = taskStatus(
      "base",
      "base#demo#previous",
      "previous-machine",
    );
    previous.state = "running";
    previous.managed_run_id = previous.run_id;
    const next = {
      ...previous,
      task_id: change === "task" ? "base#demo#next" : previous.task_id,
      reg_name: "next-machine",
    };
    let finishPrevious!: (value: typeof previous) => void;
    let finishNext!: (value: typeof next) => void;
    let finishCancel!: (value: boolean) => void;
    vi.mocked(getTaskStatus).mockResolvedValueOnce(previous);
    if (change !== "cancellation")
      vi.mocked(getTaskStatus).mockReturnValueOnce(
        new Promise((resolve) => {
          finishPrevious = resolve;
        }),
      );
    vi.mocked(getTaskStatus).mockReturnValueOnce(
      new Promise((resolve) => {
        finishNext = resolve;
      }),
    );
    vi.mocked(cancelTask).mockReturnValue(
      new Promise((resolve) => {
        finishCancel = resolve;
      }),
    );
    const callbacks = {
      onBack: vi.fn(),
      onOpenTask: vi.fn(),
      onInterpretTask: vi.fn(),
      onOpenResearch: vi.fn(),
      onConnection: vi.fn(),
    };
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () =>
        root.render(
          <TaskDetailPage
            {...callbacks}
            taskId={previous.task_id}
            target="previous"
          />,
        ),
      );
      await act(async () =>
        container
          .querySelector<HTMLButtonElement>(
            change === "cancellation"
              ? ".task-detail-cancel"
              : ".task-detail-heading-actions button",
          )!
          .click(),
      );
      await act(async () =>
        root.render(
          <TaskDetailPage
            {...callbacks}
            taskId={next.task_id}
            target={change === "task" ? "previous" : "next"}
          />,
        ),
      );
      expect(container.querySelector(".task-detail-heading")).toBeNull();
      expect(container.querySelector(".task-detail-loading")).not.toBeNull();
      if (change !== "cancellation")
        expect(vi.mocked(getTaskStatus).mock.calls[1][2]?.aborted).toBe(true);
      await act(async () => finishNext(next));
      await act(async () => {
        if (change === "cancellation") finishCancel(true);
        else finishPrevious(previous);
      });
      expect(container.querySelector(".config-source code")?.textContent).toBe(
        "next-machine",
      );
      expect(
        container.querySelector<HTMLButtonElement>(".task-detail-cancel")
          ?.disabled,
      ).toBe(false);
      expect(getTaskStatus).toHaveBeenCalledTimes(
        change === "cancellation" ? 2 : 3,
      );
      expect(callbacks.onConnection).toHaveBeenCalledTimes(2);
    } finally {
      await act(async () => root.unmount());
      vi.mocked(window.confirm).mockRestore();
    }
  },
);

it("recovers from an initial request failure through retry", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("en");
  const task = taskStatus("base", "base#demo#retry", "demo");
  vi.mocked(getTaskStatus)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(task);
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <TaskDetailPage
          taskId={task.task_id}
          onBack={vi.fn()}
          onOpenTask={vi.fn()}
          onInterpretTask={vi.fn()}
          onOpenResearch={vi.fn()}
          onConnection={vi.fn()}
        />,
      ),
    );
    expect(container.querySelector(".error-banner")?.textContent).toContain(
      "offline",
    );
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>(".error-banner button")!
        .click(),
    );
    expect(container.querySelector(".error-banner")).toBeNull();
    expect(container.querySelector("h1")?.textContent).toBe(task.task_id);
  } finally {
    await act(async () => root.unmount());
  }
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

it.each(["base", "composite"] as const)(
  "shows only the %s runtime view in both languages",
  async (kind) => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    const task = taskStatus(kind, `${kind}#demo`, "demo");
    task.steps = [
      { ...task.steps[0], name: "execute" },
      {
        ...task.steps[0],
        name: "collection:open",
        label: "Open snapshot",
        parent: "execute",
        group: "collection",
        files: { data: "data.csv" },
      },
    ];
    task.output_params = {
      windows: [{ key: "open" }],
      result: "raw-output-marker",
    };
    const child = {
      node_name: "history",
      task: "history",
      task_id: "composite#history",
      run_id: "old-run-marker",
      attempt: 1,
      state: "failed" as const,
      exit_code: 1,
      error: "old-error-marker",
    };
    task.children = [
      child,
      {
        ...child,
        run_id: "new-run-marker",
        attempt: 2,
        state: "succeeded",
        error: "",
      },
      {
        ...child,
        node_name: "invalid",
        task_id: null,
        run_id: "invalid-run",
        error: "invalid inputs",
      },
    ];
    vi.mocked(getTaskStatus).mockResolvedValue(task);
    const onOpenTask = vi.fn();
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      for (const language of ["zh", "en"]) {
        await act(async () => {
          await i18n.changeLanguage(language);
        });
        await act(async () =>
          root.render(
            <TaskDetailPage
              taskId={task.task_id}
              target="remote"
              onBack={vi.fn()}
              onOpenTask={onOpenTask}
              onInterpretTask={vi.fn()}
              onOpenResearch={vi.fn()}
              onConnection={vi.fn()}
            />,
          ),
        );
        const card = container.querySelector(".task-run-card")!;
        expect(card.textContent).not.toContain("raw-output-marker");
        expect(card.textContent).not.toContain("data.csv");
        expect(
          card.querySelector(
            ".pipeline-step, .task-run-meta, .task-current-step, pre",
          ),
        ).toBeNull();
        if (kind === "composite") {
          expect(card.textContent).not.toContain("execute");
          expect(card.textContent).not.toContain("Open snapshot");
          expect(card.textContent).not.toContain("old-error-marker");
          expect(card.textContent).not.toContain("new-run-marker");
          expect(card.textContent).toContain("invalid inputs");
          expect(card.querySelectorAll(".step-item")).toHaveLength(2);
          const links =
            card.querySelectorAll<HTMLButtonElement>(".child-task-link");
          expect(links).toHaveLength(1);
          await act(async () => links[0].click());
          expect(onOpenTask).toHaveBeenLastCalledWith("composite#history");
        } else {
          expect(card.textContent).toContain("execute");
          expect(card.textContent).toContain("Open snapshot");
          expect(card.querySelectorAll(".step-substep")).toHaveLength(1);
          expect(card.querySelector(".child-task-link")).toBeNull();
        }
      }
    } finally {
      await act(async () => root.unmount());
    }
  },
);

it("shows a child empty state before any children are invoked", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("zh");
  const task = taskStatus("composite", "composite#empty", "empty");
  vi.mocked(getTaskStatus).mockResolvedValue(task);
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <TaskDetailPage
          taskId={task.task_id}
          onBack={vi.fn()}
          onOpenTask={vi.fn()}
          onInterpretTask={vi.fn()}
          onOpenResearch={vi.fn()}
          onConnection={vi.fn()}
        />,
      ),
    );
    expect(container.querySelector(".task-run-card")?.textContent).toContain(
      "暂无子任务",
    );
    expect(container.querySelector(".step-item")).toBeNull();
  } finally {
    await act(async () => root.unmount());
  }
});
