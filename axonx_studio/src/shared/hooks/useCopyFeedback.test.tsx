// @vitest-environment jsdom
import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useCopyFeedback } from "./useCopyFeedback";
let root: Root;
let container: HTMLDivElement;
let clipboard: ReturnType<typeof useCopyFeedback>;
const writeText = vi.fn();
function Harness() {
  clipboard = useCopyFeedback();
  return <span>{clipboard.copied}</span>;
}
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.useFakeTimers();
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  container = document.createElement("div");
  root = createRoot(container);
  await act(async () =>
    root.render(
      <StrictMode>
        <Harness />
      </StrictMode>,
    ),
  );
});
afterEach(async () => {
  await act(async () => root.unmount());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
it("restarts feedback on repeated copies and clears its timer on unmount", async () => {
  await act(async () => {
    await clipboard.copy("id");
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1_000);
    await clipboard.copy("id");
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1_000);
  });
  expect(container.textContent).toBe("id");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(600);
  });
  expect(container.textContent).toBe("");
  await act(async () => {
    await clipboard.copy("id");
    root.render(null);
  });
  expect(vi.getTimerCount()).toBe(0);
});
it("does not create a feedback timer when a pending copy completes after unmount", async () => {
  let finish!: () => void;
  writeText.mockReturnValue(
    new Promise<void>((resolve) => {
      finish = resolve;
    }),
  );
  let pending!: Promise<void>;
  await act(async () => {
    pending = clipboard.copy("id");
  });
  await act(async () => root.render(null));
  await act(async () => {
    finish();
    await pending;
  });
  expect(vi.getTimerCount()).toBe(0);
});
