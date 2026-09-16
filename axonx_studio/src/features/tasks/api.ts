import { callJob, remoteBody } from "../../shared/api/client";
import type { TaskInfo, TaskLogChunk, TaskStatus } from "../../types";

export const listTaskStatuses = (remoteIp?: string, signal?: AbortSignal) =>
  callJob<TaskStatus[]>(
    "list_runtime_task_statuses",
    remoteBody(remoteIp),
    signal,
  );
export const getTaskStatus = (
  taskId: string,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  callJob<TaskStatus>(
    "status",
    { task_id: taskId, ...remoteBody(remoteIp) },
    signal,
  );
export const readTaskLog = (
  taskId: string,
  offset = -1,
  limit = 65_536,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  callJob<TaskLogChunk>(
    "read_task_log",
    { task_id: taskId, offset, limit, ...remoteBody(remoteIp) },
    signal,
  );
export const listInstalledTaskInfos = (
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  callJob<TaskInfo[]>(
    "list_installed_task_infos",
    remoteBody(remoteIp),
    signal,
  );
export const cancelTask = (taskId: string, remoteIp?: string) =>
  callJob<boolean>("cancel", { task_id: taskId, ...remoteBody(remoteIp) });
export const deleteTasks = (taskIds: string[], remoteIp?: string) =>
  callJob<string[]>("delete_tasks", {
    task_ids: taskIds,
    ...remoteBody(remoteIp),
  });
export const submitTask = (
  task: string,
  values: Record<string, unknown>,
  remoteIp?: string,
) =>
  callJob<{ accepted: boolean; task: string }>("submit", {
    task,
    ...values,
    ...remoteBody(remoteIp),
  });
