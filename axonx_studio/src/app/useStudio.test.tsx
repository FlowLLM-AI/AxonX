// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listMachineOptions, machineStatus } from "../features/machines/api";
import type { MachineInfo } from "../features/machines/types";
import { AppShell } from "./AppShell";
import { defaultRoute } from "./routes";
import { useStudio } from "./useStudio";

vi.mock("../features/operations/api", () => ({
  listStudioPages: vi.fn().mockResolvedValue([]),
}));
vi.mock("../features/machines/api", () => ({
  listMachineOptions: vi.fn(),
  machineStatus: vi.fn(),
}));
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: "en" },
  }),
}));

function info(version: string): MachineInfo {
  return {
    axonx: { version, git_commit: null, git_branch: null },
    cpu: { total_cores: 4, physical_cores: 4, usage_percent: 0 },
    memory: {
      total_bytes: 1024,
      used_bytes: 0,
      available_bytes: 1024,
      usage_percent: 0,
    },
    gpus: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => (resolve = res));
  return { promise, resolve };
}

let root: Root;
let container: HTMLDivElement;
let studio: ReturnType<typeof useStudio>;

function Harness() {
  studio = useStudio();
  return <AppShell {...studio}>Page content</AppShell>;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.clearAllMocks();
  localStorage.clear();
  window.history.replaceState(null, "", "#local/home/overview");
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  vi.mocked(listMachineOptions).mockResolvedValue([
    { id: "local", address: "localhost", isLocal: true, healthy: true },
    {
      id: "remote:1024",
      address: "remote:1024",
      isLocal: false,
      healthy: true,
    },
  ]);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => vi.advanceTimersByTimeAsync(0));
  await act(async () => root.unmount());
  expect(vi.getTimerCount()).toBe(0);
  container.remove();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const version = () => container.querySelector(".brand-version")?.textContent;

describe("Studio backend version", () => {
  it("shows the selected backend version on home and other pages and clears it on failure", async () => {
    vi.mocked(machineStatus).mockResolvedValue(info("9.8.7"));
    await act(async () => root.render(<Harness />));
    expect(version()).toBe("v9.8.7");
    expect(container.querySelector(".studio-brand strong")?.textContent).toBe(
      "AxonXStudio",
    );
    await act(async () => studio.navigate(defaultRoute("runtime")));
    expect(version()).toBe("v9.8.7");
    vi.mocked(machineStatus).mockResolvedValue(info("3.2.1"));
    await act(async () =>
      studio.navigate(defaultRoute("runtime"), "remote:1024"),
    );
    expect(version()).toBe("v3.2.1");
    expect(machineStatus).toHaveBeenLastCalledWith(
      "remote:1024",
      expect.any(AbortSignal),
    );
    vi.mocked(machineStatus).mockRejectedValue(new Error("Offline"));
    await act(async () => vi.advanceTimersByTimeAsync(15_000));
    expect(version()).toBeUndefined();
  });

  it("aborts obsolete version requests and ignores responses from the previous machine", async () => {
    const local = deferred<MachineInfo>();
    const remote = deferred<MachineInfo>();
    vi.mocked(machineStatus)
      .mockReturnValueOnce(local.promise)
      .mockReturnValueOnce(remote.promise);
    await act(async () => root.render(<Harness />));
    const signal = vi.mocked(machineStatus).mock.calls[0][1]!;
    await act(async () =>
      studio.navigate(defaultRoute("runtime"), "remote:1024"),
    );
    expect(signal.aborted).toBe(true);
    expect(version()).toBeUndefined();
    await act(async () => local.resolve(info("old")));
    expect(version()).toBeUndefined();
    await act(async () => remote.resolve(info("current")));
    expect(version()).toBe("vcurrent");
  });
});
