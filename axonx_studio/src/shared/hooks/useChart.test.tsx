// @vitest-environment jsdom
import { init } from "echarts/core";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useChart, type ChartRenderer } from "./useChart";

vi.mock("echarts/core", () => ({
  init: vi.fn(),
  use: vi.fn(),
}));

afterEach(() => vi.unstubAllGlobals());

it("updates one chart instance and disposes observers with its surface", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const resize = vi.fn();
  const dispose = vi.fn();
  const disconnect = vi.fn();
  vi.mocked(init).mockReturnValue({ resize, dispose } as unknown as ReturnType<
    typeof init
  >);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = vi.fn();
      disconnect = disconnect;
    },
  );
  const first = vi.fn<ChartRenderer>();
  const second = vi.fn<ChartRenderer>();
  function Surface({ render }: { render: ChartRenderer }) {
    return <div ref={useChart(render)} />;
  }
  const root = createRoot(document.createElement("div"));
  await act(async () => root.render(<Surface render={first} />));
  await act(async () => root.render(<Surface render={second} />));
  expect(init).toHaveBeenCalledOnce();
  expect(first).toHaveBeenCalledOnce();
  expect(second).toHaveBeenCalledOnce();
  expect(dispose).not.toHaveBeenCalled();
  await act(async () => root.unmount());
  expect(disconnect).toHaveBeenCalledOnce();
  expect(dispose).toHaveBeenCalledOnce();
});
