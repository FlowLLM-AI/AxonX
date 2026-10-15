// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, configureClient } from "../../shared/api/client";
import { createPlayground } from "../../playground/runtime";
import OnlinePage from "./OnlinePage";
import { parseOnlineReport } from "./types";

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
const render = async (initialTaskId?: string) => {
  await act(async () => {
    root.render(
      <OnlinePage
        initialTaskId={initialTaskId}
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
  it("shows root pipeline collection, model stages and logs; comparison remains accessible", async () => {
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
    expect(container.querySelectorAll(".run-index article")).toHaveLength(2);
    await render("composite#playground_compare#demo");
    expect(container.textContent).toContain("onlinePipeline.nightly");
    expect(container.textContent).toContain("nightly-a_stock_etl");
    await render("analysis#playground_online#demo");
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
    expect(container.textContent).toContain("onlinePipeline.empty");
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
    expect(container.querySelectorAll(".run-index article")).toHaveLength(2);
    expect(container.querySelector(".online-filters")).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});
