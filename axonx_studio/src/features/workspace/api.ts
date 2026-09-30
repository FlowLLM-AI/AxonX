import { axonx } from "../../shared/api/client";
import type { WorkspaceDirectory, WorkspacePreview } from "./types";

export const listWorkspaceEntries = (
  path = "",
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<WorkspaceDirectory>(
    "list_entries",
    { path },
    { target, signal },
  );

export const listTaskRuns = (
  taskType: string,
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<WorkspaceDirectory>(
    "list_task_runs",
    { task_type: taskType },
    { target, signal },
  );

export const previewWorkspaceFile = (
  path: string,
  offset = 0,
  limit = 200,
  target?: string,
  signal?: AbortSignal,
) =>
  axonx.invoke<WorkspacePreview>(
    "preview_file",
    { path, offset, limit },
    { target, signal },
  );
export const deleteWorkspaceEntries = (paths: string[], target?: string) =>
  axonx.invoke<{ deleted: string; kind: "file" | "directory" }[]>(
    "delete_entries",
    { paths },
    { target },
  );
