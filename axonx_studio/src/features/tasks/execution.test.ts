import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { taskStatus } from "../../playground/data";
import type { StreamOptions } from "../../shared/api/event";
import { AxonXError } from "../../shared/api/response";
import { executeTaskCommand, getTaskStatus, type CommandResult } from "./api";
import { TaskExecutionStore, taskCommand } from "./execution";
import type { TaskDefinition } from "./model";

vi.mock("./api", () => ({
  executeTaskCommand: vi.fn(),
  getTaskStatus: vi.fn(),
}));
const definition: TaskDefinition = {
  name: "demo",
  task_type: "base",
  source: "native",
  plugin: null,
  description: "",
  input_schema: {},
  output_schema: {},
};
const result: CommandResult = {
  stdout: "{}",
  stderr: "",
  exit_code: 0,
  stdout_truncated: false,
  stderr_truncated: false,
};
let store: TaskExecutionStore;
let options: StreamOptions<CommandResult>;
let finish: (result: CommandResult) => void;
let fail: (error: Error) => void;
beforeEach(() => {
  vi.useFakeTimers();
  vi.resetAllMocks();
  store = new TaskExecutionStore();
  vi.mocked(getTaskStatus).mockRejectedValue(new Error("Not published yet"));
  vi.mocked(executeTaskCommand).mockImplementation((_argv, request) => {
    options = request!;
    return new Promise((resolve, reject) => {
      finish = resolve;
      fail = reject;
      request?.signal?.addEventListener(
        "abort",
        () => reject(new DOMException("Aborted", "AbortError")),
        { once: true },
      );
    });
  });
});
afterEach(async () => {
  store.dispose();
  await vi.advanceTimersByTimeAsync(0);
  vi.useRealTimers();
});

it("preserves typed arguments and literal strings without a shell", () => {
  const argv = taskCommand("demo", {
    code: "001",
    literal: "--target",
    bool: false,
    rows: ["a b", "$(pwd)"],
    config: { n: 2 },
  });
  expect(argv.slice(0, 3)).toEqual(["exec", "--task", '"demo"']);
  const inputs = Object.fromEntries(
    Array.from({ length: 5 }, (_, index) => [
      argv[index * 2 + 3],
      JSON.parse(argv[index * 2 + 4]),
    ]),
  );
  expect(inputs).toEqual({
    "--code": "001",
    "--literal": "--target",
    "--bool": false,
    "--rows": ["a b", "$(pwd)"],
    "--config": { n: 2 },
  });
  expect(() => taskCommand("demo", { target: "another-machine" })).toThrow(
    "Unsupported Task parameter",
  );
});

it("keeps a remote execution alive when its page unsubscribes", async () => {
  const listener = vi.fn();
  const unsubscribe = store.subscribe(listener);
  const run = store.start(
    definition,
    { x: 2 },
    { machineId: "remote", target: "remote:1024" },
  );
  unsubscribe();
  expect(options.target).toBe("remote:1024");
  expect(options.signal?.aborted).toBe(false);
  expect(run.taskId).toMatch(/^base#demo#studio-/);
  expect(store.snapshot()[0].state).toBe("running");
  finish(result);
  await vi.advanceTimersByTimeAsync(0);
  expect(store.snapshot()[0].state).toBe("succeeded");
});

it("observes metadata while streaming and retains a bounded log tail", async () => {
  const run = store.start(definition, {}, { machineId: "local" });
  const task = taskStatus("base", run.taskId);
  task.state = "running";
  vi.mocked(getTaskStatus).mockResolvedValue(task);
  await vi.advanceTimersByTimeAsync(200);
  expect(store.snapshot()[0].task?.task_id).toBe(run.taskId);
  options.onEvent?.({ kind: "log", content: "x".repeat(100_000) } as never);
  expect(store.snapshot()[0].log).toHaveLength(65_536);
  finish(result);
  await vi.advanceTimersByTimeAsync(0);
});

it("retains failed command stderr and exit status instead of reporting a disconnect", async () => {
  store.start(definition, {}, { machineId: "local" });
  options.onEvent?.({
    kind: "result",
    success: false,
    answer: { ...result, exit_code: 2, stderr: "Invalid x" },
    metadata: {},
  });
  fail(new AxonXError("[object Object]"));
  await vi.advanceTimersByTimeAsync(0);
  expect(store.snapshot()[0]).toMatchObject({
    state: "failed",
    exitCode: 2,
    error: "Invalid x",
  });
});

it("does not retry an interrupted command", async () => {
  store.start(definition, {}, { machineId: "local" });
  fail(new TypeError("Network interrupted"));
  await vi.advanceTimersByTimeAsync(5_000);
  expect(store.snapshot()[0].state).toBe("disconnected");
  expect(executeTaskCommand).toHaveBeenCalledTimes(1);
});

it("does not mistake an earlier same-name record for a failed rerun", async () => {
  const old = taskStatus("base", "base#demo#same");
  vi.mocked(getTaskStatus).mockResolvedValue(old);
  store.start(definition, { task_name: "same" }, { machineId: "local" });
  await vi.advanceTimersByTimeAsync(0);
  options.onEvent?.({
    kind: "result",
    success: false,
    answer: { ...result, exit_code: 2, stderr: "Validation failed" },
    metadata: {},
  });
  fail(new Error("Validation failed"));
  await vi.advanceTimersByTimeAsync(0);
  expect(store.snapshot()[0].task).toBeNull();
  expect(store.snapshot()[0].state).toBe("failed");
});

it("rejects an existing running Task before spawning a command", async () => {
  const old = taskStatus("base", "base#demo#same");
  old.state = "running";
  vi.mocked(getTaskStatus).mockResolvedValue(old);
  store.start(definition, { task_name: "same" }, { machineId: "local" });
  await vi.advanceTimersByTimeAsync(0);
  expect(executeTaskCommand).not.toHaveBeenCalled();
  expect(store.snapshot()[0].state).toBe("failed");
});

it("allows an unused custom name but rejects concurrent duplicate launches", async () => {
  vi.mocked(getTaskStatus).mockRejectedValue(
    new AxonXError("KeyError: 'base#demo#same'"),
  );
  store.start(definition, { task_name: "same" }, { machineId: "local" });
  expect(() =>
    store.start(definition, { task_name: "same" }, { machineId: "local" }),
  ).toThrow("already running");
  await vi.advanceTimersByTimeAsync(0);
  expect(executeTaskCommand).toHaveBeenCalledTimes(1);
  store.dismiss(store.snapshot()[0].id);
  expect(store.snapshot()).toHaveLength(1);
  finish(result);
  await vi.advanceTimersByTimeAsync(0);
  store.dismiss(store.snapshot()[0].id);
  expect(store.snapshot()).toHaveLength(0);
});

it("stops on the original target and checks the exact execution before termination", async () => {
  const run = store.start(
    definition,
    {},
    { machineId: "remote", target: "remote:1024" },
  );
  const complete = finish;
  const task = taskStatus("base", run.taskId);
  task.state = "running";
  vi.mocked(getTaskStatus).mockResolvedValue(task);
  await vi.advanceTimersByTimeAsync(200);
  vi.mocked(executeTaskCommand).mockResolvedValueOnce(result);
  await store.stop(run.id);
  expect(executeTaskCommand).toHaveBeenLastCalledWith(
    ["kill", "--task-id", JSON.stringify(run.taskId)],
    { target: "remote:1024" },
  );
  vi.mocked(getTaskStatus).mockResolvedValue({
    ...task,
    started_at: "2026-10-28T09:00:00Z",
  });
  await store.stop(run.id);
  expect(executeTaskCommand).toHaveBeenCalledTimes(2);
  expect(store.snapshot()[0].error).toBe("Task restarted before termination");
  complete(result);
  await vi.advanceTimersByTimeAsync(0);
});
