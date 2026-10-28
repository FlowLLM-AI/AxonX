// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OperationPage from "../features/operations/OperationPage";
import { operationPages } from "../features/operations/pages";
import { listMachineOptions, machineStatus } from "../features/runtime/machine";
import { createPlayground } from "../playground/runtime";
import { AxonXClient, configureClient } from "../shared/api/client";
import type { MachineInfo } from "../shared/api/contracts";
import { AppShell } from "./AppShell";
import { defaultRoute } from "./routes";
import { useStudio } from "./useStudio";

vi.mock("../features/runtime/machine", () => ({
  listMachineOptions: vi.fn(),
  machineStatus: vi.fn(),
}));
const translate = (key: string) => key;
vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: translate,
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
const ignoreSelection = () => {};

function Harness({ operations = false }: { operations?: boolean }) {
  studio = useStudio();
  return (
    <AppShell {...studio}>
      {operations ? (
        <OperationPage
          page={operationPages.find((page) => page.id === "online")!}
          onOptionsChange={studio.setResourceOptions}
          onSelected={ignoreSelection}
          onConnection={studio.setServiceOnline}
          onOpenTask={ignoreSelection}
        />
      ) : (
        "Page content"
      )}
    </AppShell>
  );
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
  configureClient(new AxonXClient());
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
    expect(machineStatus).toHaveBeenLastCalledWith({
      target: "remote:1024",
      signal: expect.any(AbortSignal),
    });
    vi.mocked(machineStatus).mockRejectedValue(new Error("Offline"));
    await act(async () => vi.advanceTimersByTimeAsync(60_000));
    expect(version()).toBeUndefined();
  });

  it("aborts obsolete version requests and ignores responses from the previous machine", async () => {
    const local = deferred<MachineInfo>();
    const remote = deferred<MachineInfo>();
    vi.mocked(machineStatus)
      .mockReturnValueOnce(local.promise)
      .mockReturnValueOnce(remote.promise);
    await act(async () => root.render(<Harness />));
    const signal = vi.mocked(machineStatus).mock.calls[0][0]!.signal!;
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

const groupToggle = (id: string) =>
  container.querySelector<HTMLButtonElement>(`.group-${id} > button`)!;

it("remembers group choices and opens the group when entering a page", async () => {
  vi.mocked(machineStatus).mockResolvedValue(info("1.0"));
  await act(async () => root.render(<Harness />));
  expect(
    [...container.querySelectorAll(".primary-nav-group")].map(
      (el) => el.classList[1],
    ),
  ).toEqual([
    "group-system",
    "group-operations",
    "group-research",
    "group-development",
  ]);
  expect(groupToggle("system").getAttribute("aria-expanded")).toBe("true");
  expect(groupToggle("operations").getAttribute("aria-expanded")).toBe("true");
  expect(groupToggle("research").getAttribute("aria-expanded")).toBe("false");
  expect(groupToggle("development").getAttribute("aria-expanded")).toBe(
    "false",
  );
  await act(async () => {
    groupToggle("system").click();
    groupToggle("development").click();
  });
  expect(JSON.parse(localStorage.getItem("axonx-navigation-groups")!)).toEqual({
    system: false,
    development: true,
  });
  await act(async () => root.unmount());
  root = createRoot(container);
  await act(async () => root.render(<Harness />));
  expect(groupToggle("system").getAttribute("aria-expanded")).toBe("false");
  expect(groupToggle("development").getAttribute("aria-expanded")).toBe("true");
  await act(async () => studio.navigate(defaultRoute("train")));
  expect(groupToggle("research").getAttribute("aria-expanded")).toBe("true");
  await act(async () => groupToggle("research").click());
  expect(groupToggle("research").getAttribute("aria-expanded")).toBe("false");
  await act(async () => studio.navigate(defaultRoute("predict")));
  expect(groupToggle("research").getAttribute("aria-expanded")).toBe("true");
});

it("ignores malformed group preferences and expands direct-linked pages", async () => {
  vi.mocked(machineStatus).mockResolvedValue(info("1.0"));
  localStorage.setItem("axonx-navigation-groups", "invalid-json");
  window.history.replaceState(null, "", "#local/apis/catalog");
  await act(async () => root.render(<Harness />));
  expect(groupToggle("system").getAttribute("aria-expanded")).toBe("true");
  expect(groupToggle("development").getAttribute("aria-expanded")).toBe("true");
  expect(container.querySelector(".nav-apis.active")).not.toBeNull();
});

it("keeps operation navigation available when the backend is offline", async () => {
  vi.mocked(machineStatus).mockRejectedValue(new Error("Offline"));
  await act(async () => root.render(<Harness />));
  for (const page of operationPages) {
    const button = container.querySelector<HTMLButtonElement>(
      `.nav-operation-${page.id}`,
    )!;
    expect(button.textContent).toBe(page.titleKey);
    await act(async () => button.click());
    expect(studio.route).toEqual({ section: "operations", view: page.id });
  }
});

it("retains breadcrumb options when selecting a resource and clears them on page changes", async () => {
  vi.mocked(machineStatus).mockResolvedValue(info("1.0"));
  await act(async () => root.render(<Harness />));
  const route = { section: "operations" as const, view: "data" };
  await act(async () => studio.navigate(route));
  const options = [{ value: "schedule:data_update", label: "data_update" }];
  await act(async () => studio.setResourceOptions(options));
  await act(async () =>
    studio.navigate({ ...route, resource: "schedule:data_update" }),
  );
  expect(studio.resourceOptions).toEqual(options);
  await act(async () => studio.navigate(defaultRoute("runtime")));
  expect(studio.resourceOptions).toEqual([]);
});

it("shares one clock across service health, operation reports and logs", async () => {
  const clocks = vi.spyOn(globalThis, "setInterval");
  const demo = createPlayground();
  const requests: string[] = [];
  configureClient(
    new AxonXClient(async (url, init) => {
      requests.push(String(url));
      return demo(url, init);
    }, false),
  );
  vi.mocked(machineStatus).mockResolvedValue(info("1.0"));
  await act(async () => root.render(<Harness operations />));
  expect(clocks).toHaveBeenCalledTimes(1);
  const logTab = () =>
    container.querySelector<HTMLButtonElement>(
      '[role="tab"][id$="-logs-tab"]',
    )!;
  await act(async () => logTab().click());
  const initial = requests.length;
  await act(async () => vi.advanceTimersByTimeAsync(59_000));
  expect(requests).toHaveLength(initial);
  expect(machineStatus).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1_000));
  expect(machineStatus).toHaveBeenCalledTimes(2);
  expect(logTab().getAttribute("aria-selected")).toBe("true");
  for (const job of ["list_task_statuses", "read_task_log"])
    expect(
      requests.slice(initial).filter((url) => url.includes(job)),
    ).toHaveLength(1);
  expect(
    requests.slice(initial).some((url) => url.includes("list_schedules")),
  ).toBe(false);
  await act(async () =>
    container.querySelector<HTMLButtonElement>(".rail-refresh")!.click(),
  );
  expect(machineStatus).toHaveBeenCalledTimes(3);
  expect(logTab().getAttribute("aria-selected")).toBe("true");
  clocks.mockRestore();
});
