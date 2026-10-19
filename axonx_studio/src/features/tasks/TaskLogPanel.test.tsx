// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { TaskLogPanel } from "./TaskLogPanel";
import { readTaskLog } from "./api";
import { seed } from "../../playground/fixtures";
import type { TaskMetadata } from "./types";
vi.mock("./api", () => ({ readTaskLog: vi.fn() }));
let root: Root;
let container: HTMLDivElement;
let task: TaskMetadata;
let source: string;
beforeEach(() => {
  vi.clearAllMocks();
  source = "A".repeat(464) + "B".repeat(65_536);
  task = structuredClone(seed().tasks.get("composite#playground_online#demo")!);
  vi.mocked(readTaskLog).mockImplementation(
    async (_id, offset = -1, limit = 65536) => {
      const start = offset < 0 ? Math.max(0, source.length - limit) : offset;
      const next = Math.min(source.length, start + limit);
      return {
        content: source.slice(start, next),
        start_offset: start,
        next_offset: next,
        file_size: source.length,
        has_more_before: start > 0,
        has_more_after: next < source.length,
        reset: false,
      };
    },
  );
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async () =>
  act(async () =>
    root.render(<TaskLogPanel task={task} target="selected:1024" />),
  );
it("loads the exact preceding byte range without overlapping the existing log", async () => {
  await render();
  expect(container.querySelector("pre")?.textContent).toBe("B".repeat(65_536));
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".load-earlier")!.click(),
  );
  expect(container.querySelector("pre")?.textContent).toBe(source);
  expect(vi.mocked(readTaskLog).mock.calls[1]?.slice(0, 4)).toEqual([
    task.task_id,
    0,
    464,
    "selected:1024",
  ]);
  expect(
    vi.mocked(readTaskLog).mock.calls.every((call) => call[5] === task.run_id),
  ).toBe(true);
});
it("drains all remaining pages when the task finishes", async () => {
  source = "initial\n";
  task.state = "running";
  await render();
  source += "C".repeat(180_000) + "FINAL-LINE";
  task = { ...task, state: "succeeded" };
  await render();
  expect(container.querySelector("pre")?.textContent).toBe(source);
  expect(vi.mocked(readTaskLog).mock.calls.length).toBeGreaterThan(2);
});
it("retains a bounded tail and disables invalid history offsets after trimming", async () => {
  source = "initial\n";
  task.state = "running";
  await render();
  source += "D".repeat(700_000) + "FINAL-LINE";
  task = { ...task, state: "succeeded" };
  await render();
  expect(
    container.querySelector("pre")?.textContent?.endsWith("FINAL-LINE"),
  ).toBe(true);
  expect(
    container.querySelector("pre")!.textContent!.length,
  ).toBeLessThanOrEqual(524288);
});
it("shows the error without mixing logs when the server rejects a replacement run", async () => {
  vi.mocked(readTaskLog).mockRejectedValue(new Error("Task run changed"));
  await render();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "Task run changed",
  );
  expect(container.querySelector("pre")?.textContent).toBe(
    i18n.t("taskDetail.logEmpty"),
  );
});

it("follows a completed replica every 60 seconds using its replicated log", async () => {
  vi.useFakeTimers();
  Object.defineProperty(document, "hidden", {
    value: false,
    configurable: true,
  });
  task.log_path = "";
  task.state = "succeeded";
  task.replica = {
    purpose: "display",
    snapshot: null,
    source_digest: "a".repeat(64),
    policy_digest: "b".repeat(64),
    files: {},
    omitted: {},
    source_log_path: "",
    log: { path: "display/log.log", start: 0, end: source.length },
  };
  try {
    await render();
    const calls = vi.mocked(readTaskLog).mock.calls.length;
    source += "FINAL-SYNC";
    await act(async () => vi.advanceTimersByTimeAsync(59_999));
    expect(vi.mocked(readTaskLog).mock.calls.length).toBe(calls);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(container.querySelector("pre")?.textContent).toContain("FINAL-SYNC");
  } finally {
    vi.useRealTimers();
  }
});
