// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useRefresh } from "./useRefresh";

let root: Root;
let container: HTMLDivElement;
let refresh: () => Promise<void>;
function Harness({ load }: { load: (signal: AbortSignal) => Promise<void> }) {
  refresh = useRefresh(load, true, true);
  return null;
}
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.useFakeTimers();
  container = document.createElement("div");
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  expect(vi.getTimerCount()).toBe(0);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
it("deduplicates immediate, manual and automatic refreshes", async () => {
  let finish!: () => void;
  const load = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  await act(async () => root.render(<Harness load={load} />));
  let request!: Promise<void>;
  await act(async () => {
    request = refresh();
  });
  await act(async () => vi.advanceTimersByTimeAsync(5_000));
  expect(load).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish();
    await request;
  });
});
it("refreshes a new subscriber while an aborted old request remains unsettled", async () => {
  let oldSignal!: AbortSignal;
  const oldLoad = vi.fn((signal: AbortSignal) => {
    oldSignal = signal;
    return new Promise<void>(() => {});
  });
  await act(async () => root.render(<Harness load={oldLoad} />));
  await act(async () => vi.advanceTimersByTimeAsync(5_000));
  const next = vi.fn().mockResolvedValue(undefined);
  await act(async () => root.render(<Harness load={next} />));
  expect(oldSignal.aborted).toBe(true);
  await act(async () => vi.advanceTimersByTimeAsync(5_000));
  expect(next).toHaveBeenCalledTimes(2);
  await act(async () => refresh());
  expect(next).toHaveBeenCalledTimes(3);
});

it("pauses in the background and refreshes once when the page becomes visible", async () => {
  const load = vi.fn().mockResolvedValue(undefined);
  await act(async () => root.render(<Harness load={load} />));
  expect(load).toHaveBeenCalledTimes(1);
  const visibility = async (hidden: boolean) =>
    act(async () => {
      Object.defineProperty(document, "hidden", {
        value: hidden,
        configurable: true,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
  try {
    await visibility(true);
    await act(async () => vi.advanceTimersByTimeAsync(15_000));
    expect(load).toHaveBeenCalledTimes(1);
    await visibility(false);
    expect(load).toHaveBeenCalledTimes(2);
    await act(async () => vi.advanceTimersByTimeAsync(4_000));
    expect(load).toHaveBeenCalledTimes(2);
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    expect(load).toHaveBeenCalledTimes(3);
  } finally {
    Reflect.deleteProperty(document, "hidden");
  }
});
