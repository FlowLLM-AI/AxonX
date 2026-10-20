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
import { taskStatus, studioPages } from "../../playground/fixtures";
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
const render = async (initialTaskId?: string, pageId = "online") => {
  await act(async () => {
    root.render(
      <OperationPage
        page={studioPages.find((page) => page.id === pageId)!}
        onOptionsChange={onOptionsChange}
        initialResource={initialTaskId}
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

it("selects schedules without hiding grouped or ungrouped runs", async () => {
  await render("api#playground_download#demo", "data");
  expect(
    container.querySelectorAll('.run-index article[data-kind="task"]'),
  ).toHaveLength(2);
  expect(container.querySelector(".online-report")?.textContent).toContain(
    "Synthetic data update",
  );
  expect(container.textContent).not.toContain("Synthetic nightly download");
  const group =
    container.querySelector<HTMLDetailsElement>(".operation-group")!;
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".operation-schedule")!.click(),
  );
  expect(onSelected).toHaveBeenLastCalledWith("schedule:data_update");
  expect(group.open).toBe(true);
  await render("schedule:data_update", "data");
  expect(container.querySelector(".schedule-card")?.textContent).toContain(
    "data_update",
  );
  expect(container.querySelector(".online-report")).toBeNull();
  expect(
    container.querySelectorAll('.run-index article[data-kind="task"]'),
  ).toHaveLength(2);
  expect(
    container.querySelector(".operation-ungrouped")?.textContent,
  ).toContain("Synthetic data update");
  expect(container.querySelector(".operation-group")?.textContent).toContain(
    "Scheduled data update",
  );
});

it("opens a persisted Job execution separately from its schedule configuration", async () => {
  await render("trigger:demo-sync", "sync");
  expect(
    container.querySelector(".operation-job-report")?.textContent,
  ).toContain("workspace_sync");
  expect(
    container.querySelector(".operation-sync-totals")?.textContent,
  ).toContain("operations.metrics.uploaded");
  expect(container.querySelector(".schedule-card")).toBeNull();
  expect(container.querySelector(".operation-schedule")).not.toBeNull();
});

it("keeps breadcrumb resources populated when selecting another resource on the same page", async () => {
  await render(undefined, "data");
  expect(onOptionsChange).toHaveBeenLastCalledWith(
    expect.arrayContaining([
      { value: "schedule:data_update", label: "data_update" },
      expect.objectContaining({ value: "api#playground_download#demo" }),
    ]),
  );
});

it("keeps schedule branches collapsed when the page refreshes", async () => {
  await render("schedule:data_update", "data");
  const branch =
    container.querySelector<HTMLDetailsElement>(".operation-group")!;
  await act(async () => {
    branch.open = false;
    branch.dispatchEvent(new Event("toggle"));
  });
  await render("api#playground_download#demo", "data");
  expect(branch.open).toBe(false);
  expect(
    container.querySelectorAll(".operation-ungrouped article"),
  ).toHaveLength(1);
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
      1,
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
    expect(container.querySelectorAll(".operation-ungrouped")).toHaveLength(
      pageId === "sync" ? 0 : 1,
    );
    if (pageId === "online" || pageId === "nightly")
      expect(container.querySelector(".operation-group")).toBeNull();
  },
);

it("opens the latest sync execution and keeps configuration independently selectable", async () => {
  await render(undefined, "sync");
  expect(container.querySelector(".operation-job-report")).not.toBeNull();
  expect(container.querySelector(".schedule-card")).toBeNull();
  expect(
    container.querySelector('.operation-job-report [role="tab"]'),
  ).toBeNull();
  expect(container.querySelector(".operation-sync-totals")).not.toBeNull();
  await render("schedule:workspace_sync", "sync");
  expect(container.querySelector(".schedule-card")).not.toBeNull();
  expect(container.querySelector(".operation-job-report")).toBeNull();
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
