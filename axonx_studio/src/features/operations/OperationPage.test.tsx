// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, configureClient } from "../../shared/api/client";
import { createPlayground } from "../../playground/runtime";
import OperationPage from "./OperationPage";
import { DataUpdateProgress } from "./DataUpdateProgress";
import { getTaskStatus } from "../tasks/api";
import ReportPage from "./ReportPage";
import { TaskRunReport } from "./TaskRunReport";
import { schedules, taskStatus, studioPages } from "../../playground/fixtures";
import { parseOnlineReport } from "../online/types";

const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: translate }),
}));
let root: Root;
let container: HTMLDivElement;
const onConnection = vi.fn();
const onOpenTask = vi.fn();
const onSelected = vi.fn();
const onOptionsChange = vi.fn();
const onlineSchedulePage = {
  ...studioPages.find((page) => page.id === "online")!,
  schedules: ["a_stock_online"],
};
const render = async (
  initialTaskId?: string,
  pageId = "online",
  scheduleNames?: string[],
) => {
  const page = studioPages.find((page) => page.id === pageId)!;
  await act(async () => {
    root.render(
      <OperationPage
        page={scheduleNames ? { ...page, schedules: scheduleNames } : page}
        onOptionsChange={onOptionsChange}
        initialResource={initialTaskId}
        onConnection={onConnection}
        onSelected={onSelected}
        onOpenTask={onOpenTask}
      />,
    );
  });
};

const renderOnlineSchedule = async (resource?: string) => {
  await act(async () => {
    root.render(
      <OperationPage
        page={onlineSchedulePage}
        initialResource={resource}
        onOptionsChange={onOptionsChange}
        onConnection={onConnection}
        onSelected={onSelected}
        onOpenTask={onOpenTask}
      />,
    );
  });
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  configureClient(new AxonXClient(createPlayground(), false));
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  configureClient(new AxonXClient());
});

describe("online pipeline", () => {
  it("shows root pipeline collection, model stages and logs; comparison has its own page", async () => {
    await render("composite#playground_online#demo");
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>('[role="tab"][id$="-logs-tab"]')!
        .click(),
    );
    expect(container.textContent).toContain("onlineWorkbench.baseCollection");
    expect(container.textContent).toContain("99.8%");
    expect(container.textContent).toContain("5,100");
    expect(container.textContent).toContain("onlinePipeline.chainLog");
    expect(container.querySelector(".log-content")?.textContent).toContain(
      "[demo]",
    );
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>(
          ".online-daily-workbench > header button",
        )!
        .click(),
    );
    expect(onOpenTask).toHaveBeenCalledWith("composite#playground_online#demo");
    expect(container.querySelector(".online-filters")).toBeNull();
    expect(container.querySelector(".run-index-header")).not.toBeNull();
    expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
    expect(container.textContent).not.toContain("Synthetic nightly comparison");
    await render("composite#playground_compare#demo", "nightly");
    expect(container.textContent).toContain("onlinePipeline.nightly");
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>('[role="tab"][id$="-etl-tab"]')!
        .click(),
    );
    expect(container.querySelector("pre")?.textContent).toContain(
      "a_stock_etl",
    );
    await act(async () =>
      root.render(
        <ReportPage
          taskId="analysis#playground_online#demo"
          onOpenTask={onOpenTask}
        />,
      ),
    );
    expect(container.textContent).toContain(
      "onlinePipeline.status.protocol_mismatch",
    );
    expect(container.textContent).toContain("0.0012");
    expect(onConnection).toHaveBeenCalledWith(true);
  });

  it("renders empty and request failure states", async () => {
    configureClient(
      new AxonXClient(
        async () => Response.json({ answer: [], success: true }),
        false,
      ),
    );
    await render();
    expect(container.textContent).toContain("operations.empty");
    configureClient(
      new AxonXClient(async () => {
        throw new Error("Service offline");
      }, false),
    );
    await act(async () => {
      container.querySelector<HTMLButtonElement>(".rail-refresh")!.click();
    });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      "Service offline",
    );
    expect(onConnection).toHaveBeenCalledWith(false);
  });

  it("rejects malformed persisted data instead of crashing the outcome renderer", () => {
    expect(() =>
      parseOnlineReport({
        windows: [{ key: "1445", status: "done", elapsed_seconds: "slow" }],
      }),
    ).toThrow("Invalid online report");
    expect(() => parseOnlineReport({ model_identity: { model: {} } })).toThrow(
      "Invalid online report",
    );
  });
});

it("does not mistake a failed configuration request for a missing schedule", async () => {
  configureClient(
    new AxonXClient(async () => {
      throw new Error("Service offline");
    }, false),
  );
  await render(undefined, "online", ["a_stock_online"]);
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "Service offline",
  );
  expect(container.querySelectorAll(".run-index article")).toHaveLength(0);
  expect(container.querySelector(".run-index-tools em")?.textContent).toBe("0");
  expect(container.querySelector(".schedule-card")).toBeNull();
  expect(onConnection).toHaveBeenCalledWith(false);
});

it("discovers scheduled pipelines even when the first list was empty", async () => {
  vi.useFakeTimers();
  try {
    let available = false;
    const demo = createPlayground();
    configureClient(
      new AxonXClient(async (url, init) => {
        if (String(url).includes("list_task_statuses") && !available)
          return Response.json({ answer: [], success: true });
        return demo(url, init);
      }, false),
    );
    await render();
    expect(container.querySelectorAll(".run-index article")).toHaveLength(0);
    available = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(59000);
      expect(container.querySelectorAll(".run-index article")).toHaveLength(0);
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
    expect(container.querySelector(".online-filters")).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});

it("keeps categories separate even with a direct link to another category", async () => {
  await render("composite#playground_compare#demo", "online");
  expect(container.querySelector(".online-report")).toBeNull();
  expect(container.textContent).toContain("operations.empty");
  expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
});

it.each([
  { hasTask: true, newerTask: false },
  { hasTask: true, newerTask: true },
  { hasTask: false, newerTask: false },
])(
  "merges configuration and separates submission history from the current Task (%j)",
  async ({ hasTask, newerTask }) => {
    const demo = createPlayground();
    const schedule = structuredClone(
      schedules.find((item) => item.name === "data_update")!,
    );
    schedule.name = "a_stock_online";
    schedule.cron = "0 9 * * 1-5";
    schedule.arguments = { task: "playground_online", task_name: "demo" };
    schedule.last_trigger = {
      ...schedule.last_trigger!,
      name: schedule.name,
      trigger_id: "failed-online",
      triggered_at: "2026-10-21T01:00:00Z",
      finished_at: "2026-10-21T01:00:01Z",
      state: "failed",
      error: "FileExistsError: Active Task already exists",
    };
    schedule.history = [schedule.last_trigger];
    configureClient(
      new AxonXClient(async (url, init) => {
        if (String(url).includes("list_schedules"))
          return Response.json({ answer: [schedule], success: true });
        const response = await demo(url, init);
        if (String(url).includes("list_task_statuses")) {
          const payload = await response.json();
          payload.answer = hasTask
            ? payload.answer.map((task: Record<string, unknown>) =>
                task.task_id === "composite#playground_online#demo"
                  ? {
                      ...task,
                      reg_name: "playground_online",
                      display_name: "axon2-core",
                      ...(newerTask && {
                        created_at: "2026-10-21T05:26:04Z",
                        state: "failed",
                      }),
                    }
                  : task,
              )
            : [];
          return Response.json(payload);
        }
        if (String(url).endsWith("/status") && newerTask) {
          const payload = await response.json();
          if (payload.answer.task_id === "composite#playground_online#demo")
            Object.assign(payload.answer, {
              reg_name: "playground_online",
              created_at: "2026-10-21T05:26:04Z",
              state: "failed",
              error: "Current Task execution failed",
            });
          return Response.json(payload);
        }
        return response;
      }, false),
    );

    await render("trigger:failed-online", "online", [schedule.name]);
    expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
    expect(
      container.querySelectorAll('.run-index article[data-kind="task"]'),
    ).toHaveLength(hasTask ? 1 : 0);
    expect(
      container.querySelectorAll('.run-index article[data-kind="schedule"]'),
    ).toHaveLength(hasTask ? 0 : 1);
    expect(
      container.querySelector('.run-index article[data-kind="job"]'),
    ).toBeNull();
    expect(container.querySelector(".operation-group")).toBeNull();
    expect(container.querySelector(".run-index-tools em")?.textContent).toBe(
      "1",
    );
    expect(
      container.querySelector(".schedule-plan-last")?.textContent,
    ).toContain("operations.plan.conflict");
    expect(
      container.querySelector(".schedule-plan-technical pre")?.textContent,
    ).toContain(schedule.last_trigger.error);
    expect(Boolean(container.querySelector(".online-report"))).toBe(hasTask);
    expect(onOptionsChange.mock.lastCall![0]).toHaveLength(1);
    expect(onOptionsChange.mock.lastCall![0][0].value).toBe(
      hasTask ? "composite#playground_online#demo" : "schedule:a_stock_online",
    );
    if (hasTask) {
      expect(container.querySelector(".operation-schedules")).toBeNull();
      expect(
        container.querySelector(".online-daily-workbench .schedule-plan"),
      ).not.toBeNull();
      expect(
        container.querySelector(".research-canvas > .schedule-plan"),
      ).toBeNull();
      expect(
        container.querySelectorAll(".schedule-plan [role='tab']"),
      ).toHaveLength(0);
      const button = container.querySelector<HTMLButtonElement>(
        ".online-daily-workbench > header .schedule-plan-toggle",
      )!;
      expect(button.getAttribute("aria-expanded")).toBe("true");
      expect(
        button
          .getAttribute("aria-label")
          ?.includes("operations.lastSubmissionFailed"),
      ).toBe(!newerTask);
      expect(
        Boolean(container.querySelector(".schedule-plan-last.is-history")),
      ).toBe(newerTask);
      if (newerTask) {
        expect(
          container.querySelector(".schedule-plan-last")?.textContent,
        ).toContain("operations.plan.newerTask");
        expect(container.querySelector(".schedule-plan-warning")).toBeNull();
        expect(
          container.querySelector(".online-report")?.textContent,
        ).toContain("Current Task execution failed");
        expect(container.querySelector(".run-index")?.textContent).toContain(
          "states.failed",
        );
      }
      expect(container.querySelector(".run-index")?.textContent).toContain(
        "axon2-core",
      );
      await act(async () => button.click());
      expect(button.getAttribute("aria-expanded")).toBe("false");
      expect(container.querySelector(".schedule-plan")).toBeNull();
      await act(async () => button.click());
      const technical = container.querySelector<HTMLDetailsElement>(
        ".schedule-plan-technical",
      )!;
      technical.open = true;
      await act(async () =>
        container
          .querySelector<HTMLButtonElement>('[role="tab"][id$="-logs-tab"]')!
          .click(),
      );
      const selectedTab = container.querySelector(
        '[role="tab"][id$="-logs-tab"]',
      )!;
      await act(async () =>
        container.querySelector<HTMLButtonElement>(".rail-refresh")!.click(),
      );
      expect(button.getAttribute("aria-expanded")).toBe("true");
      expect(selectedTab.getAttribute("aria-selected")).toBe("true");
      expect(technical.open).toBe(true);
    } else {
      expect(container.querySelector(".operation-schedules")).toBeNull();
      expect(container.querySelector(".schedule-plan-toggle")).toBeNull();
      expect(
        container.querySelector(".schedule-card .schedule-plan"),
      ).not.toBeNull();
      expect(container.querySelector(".schedule-card [role='tab']")).toBeNull();
    }
  },
);

it("shows Job-only synchronization without querying Task records", async () => {
  const demo = createPlayground();
  const calls: string[] = [];
  configureClient(
    new AxonXClient(async (url, init) => {
      calls.push(String(url));
      return demo(url, init);
    }, false),
  );
  await render(undefined, "sync");
  expect(calls.some((url) => url.includes("list_task_statuses"))).toBe(false);
  expect(container.textContent).not.toContain("operations.schedules");
  expect(
    container.querySelector(".operation-sync-totals")?.textContent,
  ).toContain("operations.metrics.uploaded");
  expect(
    container.querySelectorAll('.run-index article[data-kind="job"]'),
  ).toHaveLength(1);
});

it("opens schedule links on an already mounted online Task without resetting its report stage", async () => {
  const demo = createPlayground();
  const schedule = { ...structuredClone(schedules[0]), name: "a_stock_online" };
  const parent = "composite#playground_online#demo";
  schedule.last_trigger = {
    ...schedule.last_trigger!,
    name: schedule.name,
    trigger_id: "online-submit",
  };
  configureClient(
    new AxonXClient(async (url, init) => {
      if (String(url).includes("list_schedules"))
        return Response.json({ answer: [schedule], success: true });
      const response = await demo(url, init);
      if (!String(url).includes("list_task_statuses")) return response;
      const payload = await response.json();
      payload.answer = payload.answer.map(
        (item: { task_id: string; source: unknown }) =>
          item.task_id === parent
            ? {
                ...item,
                source: { kind: "submit", schedule: schedule.last_trigger },
              }
            : item,
      );
      return Response.json(payload);
    }, false),
  );
  await renderOnlineSchedule(parent);
  const button = container.querySelector<HTMLButtonElement>(
    ".schedule-plan-toggle",
  )!;
  const logs = container.querySelector<HTMLButtonElement>(
    '[role="tab"][id$="-logs-tab"]',
  )!;
  await act(async () => logs.click());
  expect(button.getAttribute("aria-expanded")).toBe("false");
  await renderOnlineSchedule("schedule:a_stock_online");
  expect(button.getAttribute("aria-expanded")).toBe("true");
  expect(logs.getAttribute("aria-selected")).toBe("true");
  await act(async () => button.click());
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".rail-refresh")!.click(),
  );
  expect(button.getAttribute("aria-expanded")).toBe("false");
  await renderOnlineSchedule("trigger:online-submit");
  expect(button.getAttribute("aria-expanded")).toBe("true");
  expect(logs.getAttribute("aria-selected")).toBe("true");
  await act(async () => button.click());
  await renderOnlineSchedule(parent);
  await renderOnlineSchedule("trigger:online-submit");
  expect(button.getAttribute("aria-expanded")).toBe("true");
});

it("keeps all actual Tasks visible and opens schedule links inside the matching Task", async () => {
  await render("api#playground_download#demo", "data");
  expect(
    container.querySelectorAll('.run-index article[data-kind="task"]'),
  ).toHaveLength(2);
  expect(
    container.querySelector('.run-index article[data-kind="schedule"]'),
  ).toBeNull();
  expect(container.querySelector(".online-report")?.textContent).toContain(
    "Synthetic data update",
  );
  expect(container.querySelector(".operation-schedules")).toBeNull();
  const scheduled = [
    ...container.querySelectorAll<HTMLButtonElement>(
      ".run-index article button",
    ),
  ].find((button) => button.textContent?.includes("Scheduled data update"))!;
  await act(async () => scheduled.click());
  expect(onSelected).toHaveBeenLastCalledWith(
    "api#playground_download#scheduled",
  );
  await render("schedule:data_update", "data");
  expect(
    container.querySelector<HTMLDetailsElement>(".operation-schedules")!.open,
  ).toBe(true);
  expect(container.querySelector(".schedule-card")?.textContent).toContain(
    "data_update",
  );
  expect(container.querySelector(".online-report")?.textContent).toContain(
    "Scheduled data update",
  );
  expect(
    container.querySelectorAll('.run-index article[data-kind="task"]'),
  ).toHaveLength(2);
});

it("opens a persisted Job with its configuration collapsed in the same detail", async () => {
  await render("trigger:demo-sync", "sync");
  expect(
    container.querySelector(".operation-job-report")?.textContent,
  ).toContain("workspace_sync");
  expect(
    container.querySelector(".operation-sync-totals")?.textContent,
  ).toContain("operations.metrics.uploaded");
  expect(
    container.querySelector<HTMLDetailsElement>(".operation-schedules")!.open,
  ).toBe(false);
  expect(container.querySelector(".schedule-card")).toBeNull();
  expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
});

it("keeps breadcrumb resources limited to the actual visible entries", async () => {
  await render(undefined, "data");
  expect(onOptionsChange.mock.lastCall![0]).toHaveLength(2);
  expect(onOptionsChange).toHaveBeenLastCalledWith(
    expect.arrayContaining([
      expect.objectContaining({ value: "api#playground_download#demo" }),
      expect.objectContaining({ value: "api#playground_download#scheduled" }),
    ]),
  );
});

it("preserves configuration and technical-detail expansion on refresh", async () => {
  await render("schedule:data_update", "data");
  const details = container.querySelector<HTMLDetailsElement>(
    ".operation-schedules",
  )!;
  await act(async () => {
    details.open = false;
    details.dispatchEvent(new Event("toggle"));
  });
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".rail-refresh")!.click(),
  );
  expect(details.open).toBe(false);
  await act(async () => {
    details.open = true;
    details.dispatchEvent(new Event("toggle"));
  });
  const technical = details.querySelector<HTMLDetailsElement>(
    ".schedule-plan-technical",
  )!;
  technical.open = true;
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".rail-refresh")!.click(),
  );
  expect(details.open).toBe(true);
  expect(technical.open).toBe(true);
  expect(container.querySelectorAll(".run-index article")).toHaveLength(2);
});

it.each(["online", "nightly", "data", "sync"])(
  "refreshes %s only after 60 seconds and allows manual refresh",
  async (pageId) => {
    vi.useFakeTimers();
    try {
      const demo = createPlayground();
      let calls = 0;
      configureClient(
        new AxonXClient(async (url, init) => {
          calls += 1;
          return demo(url, init);
        }, false),
      );
      await render(undefined, pageId);
      const initial = calls;
      await act(async () => vi.advanceTimersByTimeAsync(59_000));
      expect(calls).toBe(initial);
      await act(async () => vi.advanceTimersByTimeAsync(1_000));
      expect(calls).toBeGreaterThan(initial);
      const beforeManual = calls;
      await act(async () =>
        container.querySelector<HTMLButtonElement>(".rail-refresh")!.click(),
      );
      expect(calls).toBeGreaterThan(beforeManual);
    } finally {
      vi.useRealTimers();
    }
  },
);

it("uses one page clock and refreshes the index, report and logs together", async () => {
  vi.useFakeTimers();
  const clocks = vi.spyOn(globalThis, "setInterval");
  try {
    const demo = createPlayground();
    const calls: string[] = [];
    configureClient(
      new AxonXClient(async (url, init) => {
        calls.push(String(url));
        return demo(url, init);
      }, false),
    );
    await render();
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>('[role="tab"][id$="-logs-tab"]')!
        .click(),
    );
    expect(clocks).toHaveBeenCalledTimes(1);
    const initial = calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(59_000));
    expect(calls).toHaveLength(initial);
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    const batch = calls.slice(initial);
    expect(batch.filter((url) => url.includes("list_schedules"))).toHaveLength(
      0,
    );
    expect(
      batch.filter((url) => url.includes("list_task_statuses")),
    ).toHaveLength(1);
    expect(batch.filter((url) => url.includes("read_task_log"))).toHaveLength(
      1,
    );
    const beforeManual = calls.length;
    await act(async () =>
      container.querySelector<HTMLButtonElement>(".rail-refresh")!.click(),
    );
    const manual = calls.slice(beforeManual);
    expect(manual.some((url) => url.includes("read_task_log"))).toBe(true);
    expect(manual.some((url) => url.includes("list_task_statuses"))).toBe(true);
    expect(clocks).toHaveBeenCalledTimes(1);
  } finally {
    clocks.mockRestore();
    vi.useRealTimers();
  }
});

it.each(["online", "nightly", "data", "sync"])(
  "shows %s records without redundant source headings or empty groups",
  async (pageId) => {
    await render(undefined, pageId);
    expect(container.textContent).not.toContain("operations.manual");
    expect(container.textContent).not.toContain("operations.schedules");
    expect(container.querySelector(".operation-manual")).toBeNull();
    expect(container.querySelector(".operation-index-label")).toBeNull();
    expect(
      container.querySelectorAll(".run-index article").length,
    ).toBeGreaterThan(0);
    expect(container.querySelectorAll(".operation-index-list")).toHaveLength(1);
    expect(container.querySelector(".operation-group")).toBeNull();
  },
);

it("opens the latest sync execution and resolves its configuration link to the same entry", async () => {
  await render(undefined, "sync");
  expect(container.querySelector(".operation-job-report")).not.toBeNull();
  expect(container.querySelector(".schedule-card")).toBeNull();
  expect(
    container.querySelector('.operation-job-report [role="tab"]'),
  ).toBeNull();
  expect(container.querySelector(".operation-sync-totals")).not.toBeNull();
  await render("schedule:workspace_sync", "sync");
  expect(container.querySelector(".schedule-card")).not.toBeNull();
  expect(container.querySelector(".operation-job-report")).not.toBeNull();
  expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
});

it("combines data results and progress with a task picker and on-demand logs", async () => {
  await render("api#playground_download#demo", "data");
  const report = container.querySelector(".online-report")!;
  expect(report.querySelectorAll('[role="tab"]')).toHaveLength(3);
  expect(report.querySelector('[role="combobox"]')).not.toBeNull();
  expect(
    report.querySelector('[id$="-result-panel"] pre')?.textContent,
  ).toContain("5100");
  expect(report.querySelectorAll("table thead th")).toHaveLength(4);
  expect(report.querySelector("details")).toBeNull();
  expect(report.textContent).not.toContain("operations.stageDetails");
  expect(report.querySelector(".log-panel")).toBeNull();
  await act(async () => {
    report.querySelector<HTMLButtonElement>('[id$="-logs-tab"]')!.click();
  });
  expect(report.querySelector(".log-panel")).not.toBeNull();
});

it("omits internal bookkeeping steps but retains counts, coverage and errors", async () => {
  const task = await getTaskStatus("api#playground_download#demo");
  const step = task.steps[0];
  const internal = {
    ...step,
    name: "download_lock",
    label: "download_lock",
    completed: null,
    total: null,
  };
  task.steps = [internal];
  await act(async () => root.render(<DataUpdateProgress task={task} />));
  expect(container.textContent).toBe("");
  task.steps = [
    internal,
    step,
    {
      ...internal,
      name: "coverage",
      label: "coverage",
      metrics: { coverage: 0.98 },
    },
    {
      ...internal,
      name: "partial",
      label: "partial",
      state: "failed",
      error: "Download timeout",
    },
  ];
  await act(async () => root.render(<DataUpdateProgress task={task} />));
  expect(container.textContent).not.toContain("download_lock");
  expect(container.textContent).toContain("5,100 / 5,100");
  expect(container.textContent).toContain("98.00%");
  expect(container.textContent).toContain("Download timeout");
  expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
});

it("switches download results and logs together and refuses a replaced child Run", async () => {
  const parent = await getTaskStatus("api#playground_download#demo");
  const child = taskStatus(
    "api",
    "api#static#demo",
    "DownloadTushareStaticTask",
  );
  child.output_params = {
    rows: 1234,
    selected_apis: ["stock_basic", "trade_cal", "stock_basic"],
    flow: "DownloadTushareStaticTask",
  };
  parent.children = [
    {
      node_name: "download_tushare_static",
      task: "static",
      task_id: child.task_id,
      run_id: child.run_id,
      attempt: 1,
      state: child.state,
      exit_code: 0,
      error: "",
    },
  ];
  const daily = taskStatus("api", "api#daily#demo", "DownloadTushareDailyTask");
  daily.output_params = { selected_apis: ["daily"], attempted_count: 182 };
  parent.children.push({
    ...parent.children[0],
    node_name: "download_tushare_daily",
    task_id: daily.task_id,
    run_id: daily.run_id,
  });
  parent.output_params = { artifacts: {} };
  const logRuns: string[] = [];
  configureClient(
    new AxonXClient(async (url, init) => {
      const args = JSON.parse(String(init?.body)).arguments;
      if (String(url).includes("read_task_log")) {
        logRuns.push(args.run_id);
        return Response.json({
          success: true,
          answer: {
            content: "static task log",
            start_offset: 0,
            next_offset: 15,
            file_size: 15,
            has_more_before: false,
            has_more_after: false,
            reset: false,
          },
        });
      }
      return Response.json({
        success: true,
        answer:
          args.task_id === parent.task_id
            ? parent
            : args.task_id === daily.task_id
              ? daily
              : child,
      });
    }, false),
  );
  await act(async () =>
    root.render(<TaskRunReport task={parent} onOpenTask={onOpenTask} />),
  );
  // A composite's own output contains no API summary; overview must use both owned children.
  expect(
    JSON.parse(
      container.querySelector('[id$="-interfaces-panel"] pre')!.textContent!,
    ),
  ).toEqual(["stock_basic", "trade_cal", "daily"]);
  expect(
    container.querySelector('[id$="-result-panel"]')?.textContent,
  ).toContain("182");
  expect(
    container.querySelector('[id$="-result-panel"]')?.textContent,
  ).not.toContain("operations.noResult");
  expect(
    container.querySelector('[id$="-result-panel"]')?.textContent,
  ).toContain("1234");
  const chooseStatic = async () => {
    await act(async () =>
      container.querySelector<HTMLButtonElement>('[role="combobox"]')!.click(),
    );
    const option = [
      ...document.querySelectorAll<HTMLButtonElement>('[role="option"]'),
    ].find((option) => option.textContent === "download_tushare_static")!;
    await act(async () => option.click());
  };
  await chooseStatic();
  expect(
    container.querySelector('[id$="-result-panel"] pre')?.textContent,
  ).toContain("1234");
  expect(
    container.querySelector('[id$="-result-panel"] pre')?.textContent,
  ).not.toContain("5,100");
  await act(async () =>
    container.querySelector<HTMLButtonElement>('[id$="-logs-tab"]')!.click(),
  );
  expect(logRuns).toEqual([child.run_id]);
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>('[id$="-interfaces-tab"]')!
      .click(),
  );
  expect(
    JSON.parse(
      container.querySelector('[id$="-interfaces-panel"] pre')!.textContent!,
    ),
  ).toEqual(["stock_basic", "trade_cal"]);
  const resultPanel = container.querySelector('[id$="-result-panel"]')!;
  expect(resultPanel.textContent).not.toContain("stock_basic");
  expect(resultPanel.querySelector("details")).toBeNull();

  child.run_id = "replacement";
  await act(async () =>
    root.render(
      <TaskRunReport key="refresh" task={parent} onOpenTask={onOpenTask} />,
    ),
  );
  await chooseStatic();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "onlinePipeline.replacedChildRun",
  );
  expect(container.querySelector('[id$="-result-panel"] pre')).toBeNull();
});

it("marks bounded schedule history and only requests schedules on the selected page", async () => {
  const demo = createPlayground();
  const requested: unknown[] = [];
  configureClient(
    new AxonXClient(async (url, init) => {
      const response = await demo(url, init);
      if (!String(url).includes("list_schedules")) return response;
      requested.push(JSON.parse(String(init?.body)).arguments);
      const payload = await response.json();
      payload.answer = payload.answer.map(
        (schedule: Record<string, unknown>) => ({
          ...schedule,
          history_total: 1000,
        }),
      );
      return Response.json(payload);
    }, false),
  );
  await render(undefined, "sync");
  expect(requested).toEqual([
    { name: "workspace_sync", include_history: true, history_limit: 200 },
  ]);
  expect(container.textContent).toContain("operations.historyLimited");
});
