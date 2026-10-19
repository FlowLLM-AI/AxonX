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
  await act(async () => vi.advanceTimersByTimeAsync(60_000));
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
  await act(async () => vi.advanceTimersByTimeAsync(60_000));
  const next = vi.fn().mockResolvedValue(undefined);
  await act(async () => root.render(<Harness load={next} />));
  expect(oldSignal.aborted).toBe(true);
  await act(async () => vi.advanceTimersByTimeAsync(60_000));
  expect(next).toHaveBeenCalledTimes(2);
  await act(async () => refresh());
  expect(next).toHaveBeenCalledTimes(3);
});
