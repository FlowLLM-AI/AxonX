import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startPolling } from "./polling";

class Page extends EventTarget {
  hidden = false;
  setHidden(hidden: boolean) {
    this.hidden = hidden;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}
let page: Page;
let dispose: (() => void) | undefined;
beforeEach(() => {
  vi.useFakeTimers();
  page = new Page();
  vi.stubGlobal("document", page);
});
afterEach(() => {
  dispose?.();
  dispose = undefined;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("visible-page polling", () => {
  it("counts down and polls at the configured interval", async () => {
    const callback = vi.fn().mockResolvedValue(undefined);
    const seconds = vi.fn();
    dispose = startPolling(callback, 5, seconds);
    await vi.advanceTimersByTimeAsync(4_000);
    expect(callback).not.toHaveBeenCalled();
    expect(seconds).toHaveBeenLastCalledWith(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(callback).toHaveBeenCalledTimes(1);
    expect(seconds).toHaveBeenLastCalledWith(5);
  });
  it("pauses in the background and refreshes immediately on return", async () => {
    const callback = vi.fn().mockResolvedValue(undefined);
    dispose = startPolling(callback, 15, vi.fn(), true);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(callback).toHaveBeenCalledTimes(1);
    page.setHidden(true);
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(callback).toHaveBeenCalledTimes(1);
    page.setHidden(false);
    expect(callback).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(callback).toHaveBeenCalledTimes(3);
  });
  it("does not start even an immediate check when initially hidden", () => {
    page.hidden = true;
    const callback = vi.fn().mockResolvedValue(undefined);
    dispose = startPolling(callback, 5, vi.fn(), true);
    expect(callback).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    page.setHidden(false);
    expect(callback).toHaveBeenCalledTimes(1);
  });
  it("never overlaps a slow request, including on visibility changes", async () => {
    let finish!: () => void;
    const callback = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    dispose = startPolling(callback, 5, vi.fn(), true);
    await vi.advanceTimersByTimeAsync(20_000);
    page.setHidden(true);
    page.setHidden(false);
    expect(callback).toHaveBeenCalledTimes(1);
    finish();
    await vi.advanceTimersByTimeAsync(4_000);
    expect(callback).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(callback).toHaveBeenCalledTimes(2);
  });
  it("continues polling after a failed check", async () => {
    const callback = vi.fn().mockRejectedValue(new Error("offline"));
    dispose = startPolling(callback, 5, vi.fn(), true);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(callback).toHaveBeenCalledTimes(2);
  });
  it("aborts pending work and removes timers and listeners on cleanup", async () => {
    let signal!: AbortSignal;
    let finish!: () => void;
    const callback = vi
      .fn()
      .mockImplementation((requestSignal: AbortSignal) => {
        signal = requestSignal;
        return new Promise<void>((resolve) => {
          finish = resolve;
        });
      });
    const seconds = vi.fn();
    dispose = startPolling(callback, 5, seconds, true);
    dispose();
    const updates = seconds.mock.calls.length;
    expect(signal.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    finish();
    page.setHidden(true);
    page.setHidden(false);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(callback).toHaveBeenCalledTimes(1);
    expect(seconds).toHaveBeenCalledTimes(updates);
  });
});
