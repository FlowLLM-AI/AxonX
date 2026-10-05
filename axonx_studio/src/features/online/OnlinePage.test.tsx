// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, configureClient } from "../../shared/api/client";
import { createPlayground } from "../../playground/runtime";
import OnlinePage from "./OnlinePage";
import { parseOnlineReport } from "./types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
let root: Root;
let container: HTMLDivElement;
const onConnection = vi.fn();
const onOpenTask = vi.fn();
const onSelected = vi.fn();
const render = async () => {
  await act(async () => {
    root.render(
      <OnlinePage
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
  it("shows reconciliation, filters collection and opens task details without a backend", async () => {
    await render();
    expect(container.textContent).toContain(
      "onlinePipeline.status.protocol_mismatch",
    );
    expect(container.textContent).toContain("0.0012");
    await act(async () => {
      container
        .querySelector<HTMLButtonElement>(".online-report > header button")!
        .click();
    });
    expect(onOpenTask).toHaveBeenCalledWith("analysis#playground_online#demo");
    await act(async () => {
      Array.from(
        container.querySelectorAll<HTMLButtonElement>(".online-filters button"),
      )
        .find((button) => button.textContent === "onlinePipeline.kinds.api")!
        .click();
    });
    expect(container.textContent).toContain("99.8%");
    expect(container.textContent).toContain("onlinePipeline.status.incomplete");
    expect(container.textContent).toContain("onlinePipeline.status.skipped");
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
      container
        .querySelector<HTMLButtonElement>(".online-heading button")!
        .click();
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
