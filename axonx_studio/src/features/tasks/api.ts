import { axonx, type RequestOptions } from "../../shared/api/client";
import type {
  LogChunk,
  TaskGraph,
  TaskMetadata,
  TaskSummary,
} from "../../shared/api/contracts";
import type { TaskDefinition } from "./model";
import type { StreamOptions } from "../../shared/api/event";

export interface CommandResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
}

export const executeTaskCommand = (
  argv: string[],
  options: StreamOptions<CommandResult> = {},
) => axonx.stream<CommandResult>("cli", { argv }, options);

export const listTaskStatuses = (options: RequestOptions = {}) =>
  axonx.invoke<TaskSummary[]>(
    "list_task_statuses",
    { detail: "summary" },
    options,
  );

export const listFullTaskStatuses = (options: RequestOptions = {}) =>
  axonx.invoke<TaskMetadata[]>(
    "list_task_statuses",
    { detail: "full" },
    options,
  );

export const getTaskStatus = (taskId: string, options: RequestOptions = {}) =>
  axonx.invoke<TaskMetadata>("status", { task_id: taskId }, options);

interface ReadTaskLogArguments {
  task_id: string;
  offset?: number;
  limit?: number;
  started_at?: string;
}

export const readTaskLog = (
  { offset = -1, limit = 65_536, ...arguments_ }: ReadTaskLogArguments,
  options: RequestOptions = {},
) =>
  axonx.invoke<LogChunk>(
    "read_task_log",
    { ...arguments_, offset, limit },
    options,
  );

export const listTaskDefs = (options: RequestOptions = {}) =>
  axonx.invoke<TaskDefinition[]>("list_task_defs", {}, options);

export const getTaskGraph = (taskId: string, options: RequestOptions = {}) =>
  axonx.invoke<TaskGraph>("get_task_graph", { task_id: taskId }, options);
