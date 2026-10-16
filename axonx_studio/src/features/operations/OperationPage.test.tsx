// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, configureClient } from "../../shared/api/client";
import { createPlayground } from "../../playground/runtime";
import OperationPage from "./OperationPage";
import ReportPage from "./ReportPage";
import { studioPages } from "../../playground/fixtures";
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
const render = async (initialTaskId?: string, pageId = "online") => {
  await act(async () => {
    root.render(
      <OperationPage
        page={studioPages.find((page) => page.id === pageId)!}
        onOptionsChange={onSelected}
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
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  configureClient(new AxonXClient(createPlayground(), false));
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  configureClient(new AxonXClient());
});

describe("online pipeline", () => {
  it("shows root pipeline collection, model stages and logs; comparison has its own page", async () => {
    await render("composite#playground_online#demo");
    expect(container.textContent).toContain("onlinePipeline.collection");
    expect(container.textContent).toContain("99.8%");
    expect(container.textContent).toContain("5,100");
    expect(container.textContent).toContain("onlinePipeline.chainLog");
    expect(container.querySelector(".log-content")?.textContent).toContain(
      "[demo]",
    );
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>(".online-report > header button")!
        .click(),
    );
    expect(onOpenTask).toHaveBeenCalledWith("composite#playground_online#demo");
    expect(container.querySelector(".online-filters")).toBeNull();
    expect(container.querySelector(".run-index-header")).not.toBeNull();
    expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
    expect(container.textContent).not.toContain("Synthetic nightly comparison");
    await render("composite#playground_compare#demo", "nightly");
    expect(container.textContent).toContain("onlinePipeline.nightly");
    expect(container.textContent).toContain("nightly-a_stock_etl");
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
      await vi.advanceTimersByTimeAsync(5000);
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
  expect(container.textContent).toContain("operations.history");
  expect(container.querySelector(".operation-metrics")?.textContent).toContain(
    "operations.metrics.uploaded",
  );
  expect(container.querySelectorAll(".operation-trigger")).toHaveLength(1);
});

it("shows manual data updates while keeping nested nightly downloads in their parent", async () => {
  await render(undefined, "data");
  expect(container.querySelectorAll(".run-index article")).toHaveLength(1);
  expect(container.querySelector(".online-report")?.textContent).toContain(
    "Synthetic data update",
  );
  expect(container.textContent).not.toContain("Synthetic nightly download");
  expect(container.querySelector(".log-content")?.textContent).toContain(
    "[demo]",
  );
  await render("schedule:data_update", "data");
  expect(container.textContent).toContain("operations.noTriggers");
  expect(container.querySelector(".online-report")).toBeNull();
});
