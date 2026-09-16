import { callJob, remoteBody } from "../../shared/api/client";
import type { WorkspaceDirectory, WorkspacePreview } from "../../types";

export const listWorkspaceEntries = (
  path = "",
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  callJob<WorkspaceDirectory>(
    "list_workspace_entries",
    { path, ...remoteBody(remoteIp) },
    signal,
  );
export const previewWorkspaceFile = (
  path: string,
  offset = 0,
  limit = 200,
  remoteIp?: string,
  signal?: AbortSignal,
) =>
  callJob<WorkspacePreview>(
    "preview_workspace_file",
    { path, offset, limit, ...remoteBody(remoteIp) },
    signal,
  );
export const deleteWorkspaceEntries = (paths: string[], remoteIp?: string) =>
  callJob<{ deleted: { deleted: string; kind: "file" | "directory" }[] }>(
    "delete_workspace_entries",
    { paths, ...remoteBody(remoteIp) },
  );
