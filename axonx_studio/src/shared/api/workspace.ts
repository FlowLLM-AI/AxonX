import { axonx, type RequestOptions } from "./client";
import type {
  CsvPreview,
  DeletedEntry,
  JsonlPreview,
  MachineDiagnostics,
  MarkdownPreview,
  ParquetPreview,
  StructuredPreview,
  TextPreview,
  UnsupportedPreview,
  WorkspaceListing,
} from "./contracts";

export type WorkspacePreview =
  | UnsupportedPreview
  | TextPreview
  | MarkdownPreview
  | StructuredPreview
  | CsvPreview
  | JsonlPreview
  | ParquetPreview;

export const listWorkspaceEntries = (
  { path = "", offset = 0 }: { path?: string; offset?: number } = {},
  options: RequestOptions = {},
) => axonx.invoke<WorkspaceListing>("list_entries", { path, offset }, options);

export const previewWorkspaceFile = (
  {
    path,
    offset = 0,
    limit = 200,
  }: { path: string; offset?: number; limit?: number },
  options: RequestOptions = {},
) =>
  axonx.invoke<WorkspacePreview>(
    "preview_file",
    { path, offset, limit },
    options,
  );

export const deleteWorkspaceEntries = (
  paths: string[],
  options: RequestOptions = {},
) => axonx.invoke<DeletedEntry[]>("delete_entries", { paths }, options);

export const getWorkspaceRoot = async (options: RequestOptions = {}) => {
  const info = await axonx.invoke<MachineDiagnostics>("diagnose", {}, options);
  return info.workspace.path;
};
