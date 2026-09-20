import { axonx } from "../../shared/api/client";
import { streamJob, type JobEvent } from "../../shared/api/event";
import type {
  TaskDefinition,
  TaskHandle,
  TaskLogChunk,
  TaskStatus,
} from "./types";

export const listTaskStatuses = (remoteIp?: string, signal?: AbortSignal) =>
  axonx.invoke<TaskStatus[]>("list_task_statuses", {}, { remoteIp, signal });
export const getTaskStatus = (
  taskId: string,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskStatus>("status", { task_id: taskId }, { remoteIp, signal });
export const readTaskLog = (
  taskId: string,
  offset = -1,
  limit = 65_536,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskLogChunk>(
    "read_task_log",
    { task_id: taskId, offset, limit },
    { remoteIp, signal },
  );
export const listInstalledTaskDefinitions = (
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskDefinition[]>(
    "list_installed_task_definitions",
    {},
    { remoteIp, signal },
  );
export const cancelTask = (taskId: string, remoteIp?: string) =>
  axonx.invoke<boolean>("cancel", { task_id: taskId }, { remoteIp });
export const deleteTasks = (taskIds: string[], remoteIp?: string) =>
  axonx.invoke<string[]>("delete_tasks", { task_ids: taskIds }, { remoteIp });
export const submitTask = (
  task: string,
  values: Record<string, unknown>,
  remoteIp?: string,
) => axonx.invoke<TaskHandle>("submit", { task, ...values }, { remoteIp });

export const streamTask = (
  taskId: string,
  remoteIp: string | undefined,
  signal: AbortSignal,
  onEvent: (event: JobEvent<TaskStatus>) => void,
) =>
  streamJob<TaskStatus>(
    axonx,
    "stream_task",
    { task_id: taskId },
    {
      remoteIp,
      signal,
      onEvent,
    },
  );
