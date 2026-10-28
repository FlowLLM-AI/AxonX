// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AxonXClient, configureClient } from "../../shared/api/client";
import { UpdatePanel } from "./UpdatePanel";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
let root: Root;
let container: HTMLDivElement;
let calls: { url: string; body: { arguments: object; target?: string } }[];
let phase = "accepted";
let offline = false;
let catalog = true;
let jobNames: string[];
let submissionError = "";
let acceptedMode: string | null;
const record = () => ({
  update_id: "a".repeat(32),
  phase,
  mode: acceptedMode,
  error: phase === "failed" ? "Install failed" : null,
  before: { axonx: "1", "axonx-studio": "1" },
  after: null,
  commit: null,
});

beforeEach(() => {
  vi.useFakeTimers();
  calls = [];
  phase = "accepted";
  offline = false;
  catalog = true;
  submissionError = "";
  acceptedMode = null;
  jobNames = [
    "update_from_git",
    "update_from_pip",
    "get_update_status",
    "restart_service",
  ];
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  configureClient(
    new AxonXClient(async (url, init) => {
      if (offline) throw new Error("offline");
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      calls.push({ url, body });
      if (url === "/jobs/restart_service" && submissionError)
        return new Response(
          JSON.stringify({ success: false, answer: submissionError }),
        );
      acceptedMode =
        {
          "/jobs/update_from_git": "git",
          "/jobs/update_from_pip": "pip",
          "/jobs/restart_service": "restart",
        }[url] ?? acceptedMode;
      const answer =
        url === "/jobs" || url.startsWith("/jobs?")
          ? {
              items: catalog ? jobNames.map((name) => ({ name })) : [],
              total: catalog ? jobNames.length : 0,
            }
          : url === "/jobs/get_update_status"
            ? {
                record: acceptedMode ? record() : null,
                log: "",
              }
            : record();
      return new Response(JSON.stringify({ success: true, answer }));
    }, false),
  );
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
  configureClient(new AxonXClient());
});

it("targets the selected machine and reconnects without treating a disconnect as success", async () => {
  await act(async () =>
    root.render(<UpdatePanel target="http://remote:1024" />),
  );
  const button = container.querySelector<HTMLButtonElement>(
    "button:not([role=combobox])",
  )!;
  expect(container.querySelector("select")!.value).toBe("git");
  expect(button.disabled).toBe(true);
  const checkboxes = container.querySelectorAll<HTMLInputElement>(
    'input[type="checkbox"]',
  );
  await act(async () => checkboxes[0].click());
  await act(async () => button.click());
  const submission = calls.find(
    (call) => call.url === "/jobs/update_from_git",
  )!;
  expect(submission.body).toEqual({
    arguments: {},
    target: "http://remote:1024",
  });
  expect(container.textContent).toContain("update.phases.accepted");
  const count = calls.length;
  await act(async () => vi.advanceTimersByTimeAsync(100));
  expect(calls.length).toBe(count);
  offline = true;
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(container.textContent).toContain("update.reconnecting");
  expect(container.textContent).not.toContain("update.phases.succeeded");
  offline = false;
  phase = "failed";
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(container.textContent).toContain("Install failed");
  expect(container.textContent).toContain("update.phases.failed");
  expect(container.textContent).not.toContain("update.reload");
});

it("hides controls when update Jobs are unavailable", async () => {
  catalog = false;
  await act(async () =>
    root.render(<UpdatePanel target="http://remote:1024" />),
  );
  expect(container.textContent).toContain("update.unavailable");
  expect(
    container.querySelector<HTMLButtonElement>("button:not([role=combobox])"),
  ).toBeNull();
});

it("retries discovery after opening during a restart or before supplying a token", async () => {
  offline = true;
  await act(async () =>
    root.render(<UpdatePanel target="http://remote:1024" />),
  );
  expect(container.textContent).toContain("offline");
  offline = false;
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(container.querySelector("select")).not.toBeNull();
  expect(container.querySelector('[role="alert"]')).toBeNull();
});

it("restarts the selected service without submitting an update and reports restart status", async () => {
  await act(async () =>
    root.render(<UpdatePanel target="http://remote:1025" />),
  );
  const select = container.querySelector("select")!;
  const checkboxes = container.querySelectorAll<HTMLInputElement>(
    'input[type="checkbox"]',
  );
  const button = container.querySelector<HTMLButtonElement>(
    "button:not([role=combobox])",
  )!;
  await act(async () => {
    select.value = "restart";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(button.disabled).toBe(true);
  expect(checkboxes[0].checked).toBe(false);
  expect(container.textContent).toContain("update.restartHint");
  expect(container.textContent).toContain("update.restartConfirm");
  expect(button.textContent).toContain("update.startRestart");
  await act(async () => checkboxes[0].click());
  await act(async () => button.click());
  expect(
    calls.find((call) => call.url === "/jobs/restart_service")!.body,
  ).toEqual({
    arguments: {},
    target: "http://remote:1025",
  });
  expect(calls.some((call) => call.url.startsWith("/jobs/update_from_"))).toBe(
    false,
  );
  expect(container.textContent).toContain("update.restartPhases.accepted");
  phase = "succeeded";
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(container.textContent).toContain("update.restartPhases.succeeded");
  expect(container.textContent).toContain("update.reload");
});

it("shows only operations configured on the selected service", async () => {
  jobNames = ["update_from_git", "update_from_pip", "get_update_status"];
  await act(async () => root.render(<UpdatePanel />));
  const select = container.querySelector("select")!;
  expect(Array.from(select.options).map((option) => option.value)).toEqual([
    "git",
    "pip",
  ]);
  expect(
    container.querySelector<HTMLButtonElement>("button:not([role=combobox])"),
  ).not.toBeNull();
});

it("allows restarting services with no update Jobs", async () => {
  jobNames = ["restart_service", "get_update_status"];
  await act(async () => root.render(<UpdatePanel />));
  const select = container.querySelector("select")!;
  expect(Array.from(select.options).map((option) => option.value)).toEqual([
    "restart",
  ]);
  expect(select.value).toBe("restart");
  await act(async () =>
    container
      .querySelectorAll<HTMLInputElement>('input[type="checkbox"]')[0]
      .click(),
  );
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>("button:not([role=combobox])")!
      .click(),
  );
  expect(calls.some((call) => call.url === "/jobs/restart_service")).toBe(true);
  offline = true;
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(container.textContent).toContain("update.reconnecting");
  offline = false;
  phase = "failed";
  await act(async () => vi.advanceTimersByTimeAsync(60000));
  expect(container.textContent).toContain("update.restartPhases.failed");
  expect(container.textContent).not.toContain("update.reload");
});

it("requires status reporting before offering any operation", async () => {
  jobNames = ["restart_service"];
  await act(async () => root.render(<UpdatePanel />));
  expect(container.querySelector("select")).toBeNull();
  expect(
    container.querySelector<HTMLButtonElement>("button:not([role=combobox])"),
  ).toBeNull();
});

it("reports rejected restart requests and keeps controls available for retry", async () => {
  jobNames = ["restart_service", "get_update_status"];
  submissionError = "Active Tasks prevent restarting";
  await act(async () => root.render(<UpdatePanel />));
  await act(async () =>
    container
      .querySelectorAll<HTMLInputElement>('input[type="checkbox"]')[0]
      .click(),
  );
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>("button:not([role=combobox])")!
      .click(),
  );
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    submissionError,
  );
  expect(
    container.querySelector<HTMLButtonElement>("button:not([role=combobox])")!
      .disabled,
  ).toBe(false);
  expect(container.textContent).not.toContain("update.restartPhases.accepted");
});

it("resets state and consent when switching machines", async () => {
  await act(async () =>
    root.render(<UpdatePanel target="http://remote:1024" />),
  );
  await act(async () =>
    container
      .querySelectorAll<HTMLInputElement>('input[type="checkbox"]')[0]
      .click(),
  );
  jobNames = ["restart_service", "get_update_status"];
  await act(async () =>
    root.render(<UpdatePanel target="http://remote:1025" />),
  );
  expect(container.querySelector("select")!.value).toBe("restart");
  expect(
    container.querySelector<HTMLButtonElement>("button:not([role=combobox])")!
      .disabled,
  ).toBe(true);
  expect(calls.at(-1)?.body.target).toBe("http://remote:1025");
});
