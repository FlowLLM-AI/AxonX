// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { taskStatus } from "../../playground/data";
import { createPlayground } from "../../playground/runtime";
import { AxonXClient, configureClient } from "../../shared/api/client";
import { getTaskStatus } from "../tasks/api";
import { DataUpdateProgress } from "./DataUpdateProgress";
import OperationPage from "./OperationPage";
import { operationPages } from "./pages";
import { parseOnlineReport } from "./report";
import ReportPage from "./ReportPage";
import { TaskReport } from "./TaskReport";

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
  const page = operationPages.find((page) => page.id === pageId)!;
  await act(async () => {
    root.render(
      <OperationPage
        page={page}
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
    await render("base#playground_online#demo");
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
    expect(onOpenTask).toHaveBeenCalledWith("base#playground_online#demo");
    expect(container.querySelector(".online-filters")).toBeNull();
    expect(container.querySelector(".task-index-header")).not.toBeNull();
    expect(container.querySelectorAll(".task-index article")).toHaveLength(1);
    expect(container.textContent).not.toContain("Synthetic nightly comparison");
    await render("base#playground_compare#demo", "comparison");
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

it("keeps report kinds separate even with a direct link to another report kind", async () => {
  await render("base#playground_compare#demo", "online");
  expect(container.querySelector(".online-report")).toBeNull();
  expect(container.textContent).toContain("operations.empty");
  expect(container.querySelectorAll(".task-index article")).toHaveLength(1);
});

it("includes standalone inference while excluding comparison reports and child executions", async () => {
  const inference = taskStatus(
    "inference",
    "inference#model#standalone",
    "model",
  );
  const comparison = taskStatus(
    "analysis",
    "analysis#compare#standalone",
    "compare",
  );
  comparison.report_kind = "online";
  const child = {
    ...inference,
    task_id: "inference#model#child",
    parent_task_id: "base#pipeline#parent",
  };
  configureClient(
    new AxonXClient(
      async () =>
        Response.json({
          answer: [inference, comparison, child],
          success: true,
        }),
      false,
    ),
  );
  await render("missing-selection");
  expect(onOptionsChange).toHaveBeenLastCalledWith([
    expect.objectContaining({ value: inference.task_id }),
  ]);
  expect(container.querySelectorAll(".task-index article")).toHaveLength(1);
});

it("keeps all actual Tasks visible without submission configuration", async () => {
  await render("api#playground_download#demo", "data");
  expect(container.querySelectorAll(".task-index article")).toHaveLength(2);
  expect(container.querySelector(".online-report")?.textContent).toContain(
    "Synthetic data update",
  );
  const scheduled = [
    ...container.querySelectorAll<HTMLButtonElement>(
      ".task-index article button",
    ),
  ].find((button) => button.textContent?.includes("Scheduled data update"))!;
  await act(async () => scheduled.click());
  expect(onSelected).toHaveBeenLastCalledWith(
    "api#playground_download#scheduled",
  );
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

it.each(["online", "comparison", "data"])(
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

it.each(["online", "comparison", "data"])(
  "shows %s records without redundant source headings or empty groups",
  async (pageId) => {
    await render(undefined, pageId);
    expect(container.textContent).not.toContain("operations.manual");
    expect(container.textContent).not.toContain("operations.schedules");
    expect(container.querySelector(".operation-manual")).toBeNull();
    expect(container.querySelector(".operation-index-label")).toBeNull();
    expect(
      container.querySelectorAll(".task-index article").length,
    ).toBeGreaterThan(0);
    expect(container.querySelectorAll(".operation-index-list")).toHaveLength(1);
    expect(container.querySelector(".operation-group")).toBeNull();
  },
);

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

it("switches download results and logs together and refuses a replaced child Task", async () => {
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
      reg_name: "static",
      child_task_id: child.task_id,
      started_at: child.started_at,
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
    child_task_id: daily.task_id,
    started_at: daily.started_at,
  });
  parent.output_params = { artifacts: {} };
  const logStartTimes: string[] = [];
  configureClient(
    new AxonXClient(async (url, init) => {
      const args = JSON.parse(String(init?.body)).arguments;
      if (String(url).includes("read_task_log")) {
        logStartTimes.push(args.started_at);
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
    root.render(<TaskReport task={parent} onOpenTask={onOpenTask} />),
  );
  // A parent Task's own output contains no API summary; overview must use both owned children.
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
  expect(logStartTimes).toEqual([child.started_at]);
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

  child.started_at = "2026-01-04T00:00:00Z";
  await act(async () =>
    root.render(
      <TaskReport key="refresh" task={parent} onOpenTask={onOpenTask} />,
    ),
  );
  await chooseStatic();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "onlinePipeline.replacedChild",
  );
  expect(container.querySelector('[id$="-result-panel"] pre')).toBeNull();
});

it("selects a shared Task by ID when another branch retains an older start time", async () => {
  const parent = taskStatus("api", "api#parent#test", "Parent");
  const first = taskStatus("api", "api#first#test", "First");
  const second = taskStatus("api", "api#second#test", "Second");
  const child = taskStatus("api", "api#shared#test", "Shared");
  child.output_params = { result: 777 };
  const record = (task: typeof child, name = task.reg_name) => ({
    reg_name: task.reg_name,
    child_task_id: task.task_id,
    node_name: name,
    started_at: task.started_at,
    attempt: 1,
    state: task.state,
    exit_code: 0,
    error: "",
  });
  parent.children = [record(first), record(second)];
  first.children = [
    { ...record(child, "old-child"), started_at: "2025-01-01T00:00:00Z" },
  ];
  second.children = [record(child, "current-child")];
  const tasks = new Map(
    [parent, first, second, child].map((task) => [task.task_id, task]),
  );
  configureClient(
    new AxonXClient(async (_url, init) => {
      const args = JSON.parse(String(init?.body)).arguments;
      return Response.json({ success: true, answer: tasks.get(args.task_id) });
    }, false),
  );
  await act(async () =>
    root.render(<TaskReport task={parent} onOpenTask={onOpenTask} />),
  );
  await act(async () =>
    container.querySelector<HTMLButtonElement>('[role="combobox"]')!.click(),
  );
  const options = [
    ...document.querySelectorAll<HTMLButtonElement>('[role="option"]'),
  ];
  expect(
    options.filter((option) => option.textContent?.includes("child")),
  ).toHaveLength(1);
  await act(async () =>
    options.find((option) => option.textContent === "current-child")!.click(),
  );
  expect(
    container.querySelector('[id$="-result-panel"]')?.textContent,
  ).toContain("777");
});
