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
const record = () => ({
  update_id: "a".repeat(32),
  phase,
  mode: "git",
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
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  configureClient(
    new AxonXClient(async (url, init) => {
      if (offline) throw new Error("offline");
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      calls.push({ url, body });
      const answer = url.startsWith("/jobs?")
        ? {
            items: catalog
              ? ["update_from_git", "update_from_pip", "get_update_status"].map(
                  (name) => ({ name }),
                )
              : [],
            total: catalog ? 3 : 0,
          }
        : url === "/jobs/get_update_status"
          ? {
              record: calls.some((call) => call.url === "/jobs/update_from_git")
                ? record()
                : null,
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
  const button = container.querySelector("button")!;
  expect(container.querySelector("select")!.value).toBe("git");
  expect(button.disabled).toBe(true);
  const checkboxes = container.querySelectorAll<HTMLInputElement>(
    'input[type="checkbox"]',
  );
  await act(async () => checkboxes[0].click());
  await act(async () => checkboxes[1].click());
  await act(async () => button.click());
  const submission = calls.find(
    (call) => call.url === "/jobs/update_from_git",
  )!;
  expect(submission.body).toEqual({
    arguments: { force: true },
    target: "http://remote:1024",
  });
  expect(container.textContent).toContain("update.phases.accepted");
  const count = calls.length;
  await act(async () => vi.advanceTimersByTimeAsync(100));
  expect(calls.length).toBe(count);
  offline = true;
  await act(async () => vi.advanceTimersByTimeAsync(3000));
  expect(container.textContent).toContain("update.reconnecting");
  expect(container.textContent).not.toContain("update.phases.succeeded");
  offline = false;
  phase = "failed";
  await act(async () => vi.advanceTimersByTimeAsync(3000));
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
  expect(container.querySelector("button")).toBeNull();
});

it("retries discovery after opening during a restart or before supplying a token", async () => {
  offline = true;
  await act(async () =>
    root.render(<UpdatePanel target="http://remote:1024" />),
  );
  expect(container.textContent).toContain("offline");
  offline = false;
  await act(async () => vi.advanceTimersByTimeAsync(3000));
  expect(container.querySelector("select")).not.toBeNull();
  expect(container.querySelector('[role="alert"]')).toBeNull();
});
