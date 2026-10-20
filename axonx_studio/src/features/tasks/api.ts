import { axonx } from "../../shared/api/client";
import { streamJob, type JobEvent } from "../../shared/api/event";
import type {
  Schedule,
  TaskDefinition,
  TaskHandle,
  LogChunk,
  TaskMetadata,
  TaskSummary,
} from "./types";

export const listSchedules = (
  target?: string,
  signal?: AbortSignal,
  name?: string,
) =>
  axonx.invoke<Schedule[]>(
    "list_schedules",
    { include_history: true, history_limit: 200, ...(name ? { name } : {}) },
    { target, signal },
  );

export const listTaskStatuses = (target?: string, signal?: AbortSignal) =>
  axonx.invoke<TaskSummary[]>(
    "list_task_statuses",
    { detail: "summary" },
    { target, signal },
  );
export const listFullTaskStatuses = (target?: string, signal?: AbortSignal) =>
  axonx.invoke<TaskMetadata[]>(
    "list_task_statuses",
    { detail: "full" },
    { target, signal },
  );
export const getTaskStatus = (
  taskId: string,
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskMetadata>("status", { task_id: taskId }, { target, signal });
export const readTaskLog = (
  taskId: string,
  offset = -1,
  limit = 65_536,
  target?: string,
  signal?: AbortSignal,
  runId?: string,
) =>
  axonx.invoke<LogChunk>(
    "read_task_log",
    { task_id: taskId, offset, limit, ...(runId ? { run_id: runId } : {}) },
    { target, signal },
  );
export const listInstalledTaskDefinitions = (
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskDefinition[]>(
    "list_installed_task_definitions",
    {},
    { target, signal },
  );
export const cancelTask = (runId: string, target?: string) =>
  axonx.invoke<boolean>("cancel", { run_id: runId }, { target });
export const deleteTasks = (taskIds: string[], target?: string) =>
  axonx.invoke<string[]>("delete_tasks", { task_ids: taskIds }, { target });
export const submitTask = (
  task: string,
  values: Record<string, unknown>,
  target?: string,
) => axonx.invoke<TaskHandle>("submit", { task, ...values }, { target });

export const streamTask = (
  taskId: string,
  target: string | undefined,
  signal: AbortSignal,
  onEvent: (event: JobEvent<TaskMetadata>) => void,
) =>
  streamJob<TaskMetadata>(
    axonx,
    "stream_task",
    { task_id: taskId },
    {
      target,
      signal,
      onEvent,
    },
  );
