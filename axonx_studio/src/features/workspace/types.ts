export type WorkspaceEntryKind = "directory" | "file" | "symlink";
export type WorkspacePreviewKind =
  "text" | "markdown" | "json" | "yaml" | "csv" | "parquet" | "unsupported";

export interface WorkspaceEntry {
  name: string;
  path: string;
  kind: WorkspaceEntryKind;
  preview_kind: WorkspacePreviewKind | null;
  supported: boolean;
  size: number | null;
  modified_at: number;
}

export interface WorkspaceDirectory {
  path: string;
  entries: WorkspaceEntry[];
  truncated: boolean;
}

export interface WorkspacePreview {
  kind: WorkspacePreviewKind;
  size: number;
  content?: string;
  data?: unknown;
  truncated?: boolean;
  frontmatter?: unknown;
  frontmatter_error?: string | null;
  parse_error?: string | null;
  columns?: string[];
  rows?: unknown[][];
  schema?: { name: string; type: string; nullable: boolean }[];
  row_count?: number;
  row_group_count?: number;
  preview_limit?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
}
