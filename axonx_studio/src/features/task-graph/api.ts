import { axonx } from "../../shared/api/client";
import type { TaskGraph } from "./types";

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
