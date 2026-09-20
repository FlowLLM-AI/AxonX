import { axonx } from "../../shared/api/client";
import type { TaskGraph, TaskGraphList } from "./types";

export const listTaskGraphs = (
  query: string,
  offset: number,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskGraphList>(
    "list_task_graphs",
    { q: query, offset, limit: 50 },
    { remoteIp, signal },
  );

export const getTaskGraph = (
  taskId: string,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<TaskGraph>(
    "get_task_graph",
    { task_id: taskId },
    { remoteIp, signal },
  );
