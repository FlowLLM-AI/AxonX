// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AppRoute } from "../../app/routes";
import type { JobEvent } from "../../shared/api/event";
import AgentWorkspace from "./AgentWorkspace";
import { getAgentSession, listAgentSessions, streamAgentChat } from "./api";

vi.mock("./api", () => ({
  getAgentSession: vi.fn(),
  listAgentSessions: vi.fn(),
  streamAgentChat: vi.fn(),
  cancelAgentTurn: vi.fn(),
  deleteAgentSession: vi.fn(),
  forkAgentSession: vi.fn(),
  renameAgentSession: vi.fn(),
  tagAgentSession: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("./Composer", () => ({
  Composer: ({
    onChange,
    onSend,
  }: {
    onChange: (value: string) => void;
    onSend: () => void;
  }) => (
    <>
      <button onClick={() => onChange("hello")}>draft</button>
      <button onClick={onSend}>send</button>
    </>
  ),
}));

let root: Root;
let container: HTMLDivElement;
let finish: () => void;
let emit: (event: JobEvent<unknown>) => void;
let streamSignal: AbortSignal;
const navigate = vi.fn();
const replace = vi.fn();
const onOptionsChange = vi.fn();
const onConnection = vi.fn();

async function render(
  view: "new" | "chat",
  resource?: string,
  target = "machine-a",
) {
  await act(async () => {
    root.render(
      <AgentWorkspace
        view={view}
        resource={resource}
        target={target}
        navigate={navigate}
        replace={replace}
        onOptionsChange={onOptionsChange}
        onConnection={onConnection}
      />,
    );
  });
}

async function startTurn() {
  await render("new");
  const buttons = [...container.querySelectorAll("button")];
  await act(async () =>
    buttons.find((button) => button.textContent === "draft")!.click(),
  );
  await act(async () =>
    buttons.find((button) => button.textContent === "send")!.click(),
  );
  await act(async () => {
    emit({
      kind: "agent_message",
      session_id: "new-session",
      type_name: "SessionStart",
      message_uuid: "new-session:init",
      role: "system",
      sequence: 0,
      presentation: [],
    });
  });
  const route = replace.mock.calls.at(-1)![0] as AppRoute;
  await render("chat", route.resource);
}

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.resetAllMocks();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(listAgentSessions).mockResolvedValue([]);
  vi.mocked(getAgentSession).mockImplementation(async (id) => ({
    info: {
      file_size: null,
      custom_title: null,
      first_prompt: null,
      git_branch: null,
      cwd: null,
      tag: null,
      created_at: null,
      session_id: id,
      summary: "",
      last_modified: 0,
      backend: "claude",
    },
    messages: [],
    blocks: [],
  }));
  vi.mocked(streamAgentChat).mockImplementation(
    (_message, _id, _target, signal, onEvent) => {
      streamSignal = signal;
      emit = onEvent;
      return new Promise<void>((resolve, reject) => {
        finish = resolve;
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    },
  );
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

it("does not fetch an unfinished old session after switching conversations", async () => {
  await startTurn();
  expect(getAgentSession).not.toHaveBeenCalled();
  await render("chat", "existing-session");
  expect(streamSignal.aborted).toBe(true);
  expect(getAgentSession).toHaveBeenCalledTimes(1);
  expect(getAgentSession).toHaveBeenCalledWith(
    "existing-session",
    "machine-a",
    expect.any(AbortSignal),
  );
  expect(container.querySelector('[role="alert"]')).toBeNull();
});

it("ignores late stream events and reconciliation after changing targets", async () => {
  await startTurn();
  await render("new", undefined, "machine-b");
  await act(async () => {
    emit({
      kind: "result",
      success: true,
      answer: "",
      metadata: { terminal_reason: "aborted_streaming" },
    });
    finish();
  });
  expect(streamSignal.aborted).toBe(true);
  expect(getAgentSession).not.toHaveBeenCalled();
  expect(container.querySelector('[role="alert"]')).toBeNull();
});

it("still reconciles a completed turn with the selected service", async () => {
  await startTurn();
  await act(async () => finish());
  expect(getAgentSession).toHaveBeenCalledWith(
    "new-session",
    "machine-a",
    expect.any(AbortSignal),
  );
  expect(listAgentSessions).toHaveBeenCalledTimes(2);
});

it("cancels pending reconciliation when the same session is selected on another machine", async () => {
  await startTurn();
  let fail!: (reason: Error) => void;
  vi.mocked(getAgentSession).mockImplementationOnce(
    () =>
      new Promise((_resolve, reject) => {
        fail = reject;
      }),
  );
  await act(async () => finish());
  const signal = vi.mocked(getAgentSession).mock.calls[0][2]!;
  expect(signal.aborted).toBe(false);
  await render("chat", "new-session", "machine-b");
  expect(signal.aborted).toBe(true);
  await act(async () => fail(new Error("Old machine session not found")));
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(listAgentSessions).toHaveBeenCalledTimes(2);
  expect(listAgentSessions).toHaveBeenLastCalledWith(
    "machine-b",
    expect.any(AbortSignal),
  );
});

it("ignores an obsolete history failure after selecting another session", async () => {
  let fail!: (reason: Error) => void;
  vi.mocked(getAgentSession).mockImplementationOnce(
    () =>
      new Promise((_resolve, reject) => {
        fail = reject;
      }),
  );
  await render("chat", "old-session");
  const signal = vi.mocked(getAgentSession).mock.calls[0][2]!;
  await render("chat", "existing-session");
  expect(signal.aborted).toBe(true);
  await act(async () => fail(new Error("Old session not found")));
  expect(container.querySelector('[role="alert"]')).toBeNull();
  expect(onConnection).not.toHaveBeenCalledWith(false);
});

it("clears the session-list loading state when a post-turn refresh is cancelled", async () => {
  await startTurn();
  vi.mocked(listAgentSessions).mockImplementationOnce(
    (_target, signal) =>
      new Promise((_resolve, reject) => {
        signal!.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      }),
  );
  await act(async () => finish());
  expect(container.querySelector(".agent-session-loading")).not.toBeNull();
  await render("chat", "existing-session");
  expect(container.querySelector(".agent-session-loading")).toBeNull();
  expect(container.querySelector('[role="alert"]')).toBeNull();
});
