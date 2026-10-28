import { useSyncExternalStore } from "react";
import type { TaskMetadata } from "../../shared/api/contracts";
import { AxonXError } from "../../shared/api/response";
import { errorMessage } from "../../shared/lib/errors";
import { executeTaskCommand, getTaskStatus, type CommandResult } from "./api";
import type { TaskDefinition } from "./model";

export interface TaskExecution {
  id: string;
  taskId: string;
  definition: string;
  machineId: string;
  target?: string;
  state: "starting" | "running" | "succeeded" | "failed" | "disconnected";
  task: TaskMetadata | null;
  log: string;
  error: string;
  exitCode?: number;
  stopping: boolean;
}

export const executionActive = (run: TaskExecution) =>
  run.state === "starting" || run.state === "running";

const reserved = new Set([
  "task",
  "target",
  "token",
  "stream",
  "stream_format",
  "client_timeout",
  "workspace_dir",
  "log_dir",
  "timezone",
  "execution_target",
  "log_to_console",
  "log_to_file",
  "environment",
]);

export function taskCommand(
  definition: string,
  inputs: Record<string, unknown>,
) {
  const argv = ["exec", "--task", JSON.stringify(definition)];
  for (const [name, value] of Object.entries(inputs)) {
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(name) || reserved.has(name))
      throw new Error(`Unsupported Task parameter: ${name}`);
    // JSON quoting preserves strings such as "001", "false", and "--target".
    // argv is passed directly to the process; no shell command is constructed.
    argv.push(`--${name.replaceAll("_", "-")}`, JSON.stringify(value));
  }
  return argv;
}

function commandResult(value: unknown): value is CommandResult {
  return (
    value !== null &&
    typeof value === "object" &&
    "exit_code" in value &&
    typeof value.exit_code === "number" &&
    "stdout" in value &&
    typeof value.stdout === "string" &&
    "stderr" in value &&
    typeof value.stderr === "string"
  );
}

/** Own execution connections independently of pages and the selected machine. */
export class TaskExecutionStore {
  private runs: TaskExecution[] = [];
  private readonly listeners = new Set<() => void>();
  private readonly controllers = new Map<string, AbortController>();
  readonly snapshot = () => this.runs;
  readonly subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private update(id: string, patch: Partial<TaskExecution>) {
    this.runs = this.runs.map((run) =>
      run.id === id ? { ...run, ...patch } : run,
    );
    for (const listener of this.listeners) listener();
  }
  private append(id: string, content: string) {
    const run = this.runs.find((run) => run.id === id);
    if (run) this.update(id, { log: (run.log + content).slice(-65_536) });
  }
  start(
    definition: TaskDefinition,
    inputs: Record<string, unknown>,
    location: { machineId: string; target?: string },
  ): TaskExecution {
    const name =
      inputs.task_name || `studio-${crypto.randomUUID().slice(0, 18)}`;
    if (typeof name !== "string" || !/^[A-Za-z0-9-]{1,32}$/.test(name))
      throw new Error(
        "task_name must contain 1–32 letters, digits, or hyphens",
      );
    const taskId = `${definition.task_type}#${definition.name}#${name}`;
    if (
      this.runs.some(
        (run) =>
          executionActive(run) &&
          run.taskId === taskId &&
          run.target === location.target,
      )
    )
      throw new Error(`Task is already running: ${taskId}`);
    const argv = taskCommand(definition.name, { ...inputs, task_name: name });
    const run: TaskExecution = {
      id: crypto.randomUUID(),
      taskId,
      definition: definition.name,
      ...location,
      state: "starting",
      task: null,
      log: "",
      error: "",
      stopping: false,
    };
    this.runs = [run, ...this.runs];
    const controller = new AbortController();
    this.controllers.set(run.id, controller);
    this.update(run.id, {});
    void this.execute(run, argv, controller, Boolean(inputs.task_name));
    return run;
  }
  private async execute(
    run: TaskExecution,
    argv: string[],
    controller: AbortController,
    named: boolean,
  ) {
    let previous: string | undefined;
    let startedAt: string | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let settled = false;
    let terminal: CommandResult | undefined;
    let receivedResult = false;
    let observing: Promise<void> | undefined;
    const options = { target: run.target, signal: controller.signal };
    const read = async () => {
      try {
        const task = await getTaskStatus(run.taskId, options);
        if (!controller.signal.aborted && task.started_at !== previous) {
          if (startedAt && task.started_at !== startedAt) {
            this.update(run.id, {
              error:
                "Task was restarted by another execution; the original record is no longer available",
            });
            return;
          }
          startedAt = task.started_at;
          this.update(run.id, { task });
        }
      } catch {
        /* The record may not exist yet; command errors are reported below. */
      }
    };
    const observe = () =>
      (observing ??= read().finally(() => {
        observing = undefined;
      }));
    const poll = async () => {
      await observe();
      if (!settled && !controller.signal.aborted)
        timer = setTimeout(() => void poll(), 1_000);
    };
    try {
      // A failed rerun must never open the previous execution's record.
      if (named) {
        try {
          const task = await getTaskStatus(run.taskId, options);
          previous = task.started_at;
          if (task.state === "running" || task.replica)
            throw new Error(
              "Choose a new task_name: the existing Task is running or is a read-only replica",
            );
        } catch (reason) {
          if (!(
            reason instanceof AxonXError &&
            reason.message === `KeyError: '${run.taskId}'`
          ))
            throw reason;
        }
      }
      this.update(run.id, { state: "running" });
      timer = setTimeout(() => void poll(), 200);
      const result = await executeTaskCommand(argv, {
        ...options,
        onEvent: (event) => {
          if (event.kind === "log") this.append(run.id, event.content);
          if (event.kind === "result") {
            receivedResult = true;
            if (commandResult(event.answer)) terminal = event.answer;
          }
        },
      });
      if (!commandResult(result))
        throw new Error("Invalid CLI execution result");
      this.update(run.id, {
        state: result.exit_code === 0 ? "succeeded" : "failed",
        exitCode: result.exit_code,
      });
    } catch (reason) {
      this.update(run.id, {
        state:
          receivedResult ||
          !timer ||
          (reason instanceof AxonXError &&
            reason.status !== undefined &&
            reason.status >= 400)
            ? "failed"
            : "disconnected",
        exitCode: terminal?.exit_code,
        error: terminal
          ? terminal.stderr.trim() || `Exit code: ${terminal.exit_code}`
          : errorMessage(reason),
      });
    } finally {
      settled = true;
      clearTimeout(timer);
      await observing;
      await observe();
      this.controllers.delete(run.id);
    }
  }
  async stop(id: string) {
    const run = this.runs.find((run) => run.id === id);
    if (!run || !executionActive(run) || !run.task || run.stopping) return;
    this.update(id, { stopping: true });
    try {
      const current = await getTaskStatus(run.taskId, { target: run.target });
      if (current.started_at !== run.task.started_at)
        throw new Error("Task restarted before termination");
      await executeTaskCommand(
        ["kill", "--task-id", JSON.stringify(run.taskId)],
        { target: run.target },
      );
      this.update(id, {
        task: await getTaskStatus(run.taskId, { target: run.target }),
      });
    } catch (reason) {
      this.update(id, { error: errorMessage(reason) });
    } finally {
      this.update(id, { stopping: false });
    }
  }
  dismiss(id: string) {
    this.runs = this.runs.filter(
      (run) => run.id !== id || executionActive(run),
    );
    for (const listener of this.listeners) listener();
  }
  dispose() {
    for (const controller of this.controllers.values()) controller.abort();
  }
}

export const taskExecutions = new TaskExecutionStore();
export const useTaskExecutions = (store = taskExecutions) =>
  useSyncExternalStore(store.subscribe, store.snapshot);
