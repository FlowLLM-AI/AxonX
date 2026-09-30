import { axonx } from "../../shared/api/client";
import { streamJob, type JobEvent } from "../../shared/api/event";
import type {
  TaskDefinition,
  TaskHandle,
  TaskLogChunk,
  TaskStatus,
} from "./types";

export const listTaskStatuses = (target?: string, signal?: AbortSignal) =>
  axonx.invoke<TaskStatus[]>("list_task_statuses", {}, { target, signal });
export const getTaskStatus = (
  taskId: string,
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskStatus>("status", { task_id: taskId }, { target, signal });
export const readTaskLog = (
  taskId: string,
  offset = -1,
  limit = 65_536,
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskLogChunk>(
    "read_task_log",
    { task_id: taskId, offset, limit },
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
export const cancelTask = (taskId: string, target?: string) =>
  axonx.invoke<boolean>("cancel", { task_id: taskId }, { target });
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
  onEvent: (event: JobEvent<TaskStatus>) => void,
) =>
  streamJob<TaskStatus>(
    axonx,
    "stream_task",
    { task_id: taskId },
    {
      target,
      signal,
      onEvent,
    },
  );
