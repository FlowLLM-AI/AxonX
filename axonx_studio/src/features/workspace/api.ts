import { callJob, remoteBody } from "../../shared/api/client";
import type { WorkspaceDirectory, WorkspacePreview } from "../../types";

export const listWorkspaceEntries = (
  path = "",
  remoteIp?: string,
  signal?: AbortSignal,
  requireMetadata = false,
) =>
  callJob<WorkspaceDirectory>(
    "list_entries",
    {
      path,
      ...(requireMetadata ? { require_metadata: true } : {}),
      ...remoteBody(remoteIp),
    },
    signal,
  );
export const previewWorkspaceFile = (
  path: string,
  offset = 0,
  limit = 200,
  remoteIp?: string,
  full = false,
  signal?: AbortSignal,
) =>
  callJob<WorkspacePreview>(
    "preview_file",
    { path, offset, limit, full, ...remoteBody(remoteIp) },
    signal,
  );
export const deleteWorkspaceEntries = (paths: string[], remoteIp?: string) =>
  callJob<{ deleted: string; kind: "file" | "directory" }[]>(
    "delete_entries",
    { paths, ...remoteBody(remoteIp) },
  );
