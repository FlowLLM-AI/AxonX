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

interface PreviewBase {
  size: number;
}

export interface UnsupportedPreview extends PreviewBase {
  kind: "unsupported";
}

export interface TextPreview extends PreviewBase {
  kind: "text";
  content: string;
  truncated: boolean;
}

export interface MarkdownPreview extends PreviewBase {
  kind: "markdown";
  content: string;
  frontmatter: unknown;
  frontmatter_error: string | null;
  truncated: boolean;
}

export interface StructuredPreview extends PreviewBase {
  kind: "json" | "yaml";
  content: string;
  data: unknown;
  parse_error: string | null;
  truncated: boolean;
}

export interface CsvPreview extends PreviewBase {
  kind: "csv";
  columns: string[];
  rows: unknown[][];
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface ParquetPreview extends PreviewBase {
  kind: "parquet";
  columns: string[];
  rows: unknown[][];
  column_schema: { name: string; type: string; nullable: boolean }[];
  row_count: number;
  row_group_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export type WorkspacePreview =
  | UnsupportedPreview
  | TextPreview
  | MarkdownPreview
  | StructuredPreview
  | CsvPreview
  | ParquetPreview;
