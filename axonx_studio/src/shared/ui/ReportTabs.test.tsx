// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { useRefresh } from "../hooks/useRefresh";
import { ReportTabs } from "./ReportTabs";

let root: Root;
let container: HTMLDivElement;
let refresh: () => Promise<void>;
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

function Panel({ load }: { load: (signal: AbortSignal) => Promise<string> }) {
  const { data, reload } = useAsyncResource(load);
  refresh = useRefresh(reload);
  const [count, setCount] = useState(0);
  return (
    <button onClick={() => setCount(count + 1)}>
      {data}:{count}
    </button>
  );
}
async function select(id: string) {
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>(`[role="tab"][id$="-${id}-tab"]`)!
      .click(),
  );
}

it("loads only visible nested panels, aborts hidden work, and retains controls", async () => {
  const load = vi.fn(async (signal: AbortSignal) => {
    signal.throwIfAborted();
    return "rows";
  });
  const other = vi.fn(async (signal: AbortSignal) => {
    signal.throwIfAborted();
    return "other";
  });
  await act(async () =>
    root.render(
      <ReportTabs
        tabs={[
          { id: "overview", label: "Overview", content: "Summary" },
          {
            id: "details",
            label: "Details",
            content: (
              <ReportTabs
                tabs={[
                  { id: "rows", label: "Rows", content: <Panel load={load} /> },
                  {
                    id: "other",
                    label: "Other",
                    content: <Panel load={other} />,
                  },
                ]}
              />
            ),
          },
        ]}
      />,
    ),
  );
  await act(async () => vi.advanceTimersByTimeAsync(10_000));
  expect(load).not.toHaveBeenCalled();
  expect(other).not.toHaveBeenCalled();
  await select("details");
  expect(load).toHaveBeenCalledTimes(1);
  expect(other).not.toHaveBeenCalled();
  const button = container.querySelector<HTMLButtonElement>(
    '[role="tabpanel"][id$="-rows-panel"] button',
  )!;
  await act(async () => button.click());
  await act(async () => vi.advanceTimersByTimeAsync(5_000));
  expect(load).toHaveBeenCalledTimes(2);
  const signal = load.mock.calls.at(-1)![0];
  await select("overview");
  expect(signal.aborted).toBe(true);
  await act(async () => {
    await refresh();
    await vi.advanceTimersByTimeAsync(10_000);
  });
  expect(load).toHaveBeenCalledTimes(2);
  expect(other).not.toHaveBeenCalled();
  await select("details");
  expect(load).toHaveBeenCalledTimes(3);
  expect(button.textContent).toBe("rows:1");
  await select("other");
  expect(other).toHaveBeenCalledTimes(1);
  const before = load.mock.calls.length;
  await act(async () => refresh());
  expect(load).toHaveBeenCalledTimes(before);
  expect(other).toHaveBeenCalledTimes(2);
});
