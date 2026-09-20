import { axonx } from "../../shared/api/client";
import type { WorkspaceDirectory, WorkspacePreview } from "./types";

export const listWorkspaceEntries = (
  path = "",
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<WorkspaceDirectory>(
    "list_entries",
    { path },
    { remoteIp, signal },
  );

export const listTaskRuns = (
  taskType: string,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<WorkspaceDirectory>(
    "list_task_runs",
    { task_type: taskType },
    { remoteIp, signal },
  );

export const previewWorkspaceFile = (
  path: string,
  offset = 0,
  limit = 200,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<WorkspacePreview>(
    "preview_file",
    { path, offset, limit },
    { remoteIp, signal },
  );
export const deleteWorkspaceEntries = (paths: string[], remoteIp?: string) =>
  axonx.invoke<{ deleted: string; kind: "file" | "directory" }[]>(
    "delete_entries",
    { paths },
    { remoteIp },
  );
