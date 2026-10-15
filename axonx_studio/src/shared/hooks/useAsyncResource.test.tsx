// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { useAsyncResource } from "./useAsyncResource";

it("never exposes another selection's data or accepts a late aborted response", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const host = document.createElement("div");
  const root = createRoot(host);
  let finishA!: (value: string) => void;
  let finishB!: (value: string) => void;
  const loadA = vi.fn((signal: AbortSignal) => {
    signal.throwIfAborted();
    return new Promise<string>((resolve) => {
      finishA = resolve;
    });
  });
  const loadB = vi.fn((signal: AbortSignal) => {
    signal.throwIfAborted();
    return new Promise<string>((resolve) => {
      finishB = resolve;
    });
  });
  const observations: { name: string; data: string | null }[] = [];
  function View({
    name,
    load,
  }: {
    name: string;
    load: (signal: AbortSignal) => Promise<string>;
  }) {
    const { data, loading } = useAsyncResource(load);
    observations.push({ name, data });
    return <span>{loading ? "loading" : data}</span>;
  }
  try {
    await act(async () => root.render(<View name="a" load={loadA} />));
    await act(async () => root.render(<View name="b" load={loadB} />));
    expect(loadA.mock.calls[0][0].aborted).toBe(true);
    await act(async () => finishB("machine-b"));
    await act(async () => finishA("machine-a"));
    expect(host.textContent).toBe("machine-b");
    expect(
      observations
        .filter((entry) => entry.name === "b")
        .every((entry) => entry.data !== "machine-a"),
    ).toBe(true);
    // Switching a loader hides an already completed previous resource on the first render.
    const loadC = async () => "machine-c";
    await act(async () => root.render(<View name="c" load={loadC} />));
    expect(
      observations
        .filter((entry) => entry.name === "c")
        .some((entry) => entry.data === "machine-b"),
    ).toBe(false);
    expect(host.textContent).toBe("machine-c");
  } finally {
    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  }
});
