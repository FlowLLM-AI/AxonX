import type {
  WorkspaceEntry,
  UnsupportedPreview,
  TextPreview,
  MarkdownPreview,
  StructuredPreview,
  CsvPreview,
  JsonlPreview,
  ParquetPreview,
} from "../../shared/api/contracts";
export type {
  WorkspaceEntry,
  WorkspaceListing,
  UnsupportedPreview,
  TextPreview,
  MarkdownPreview,
  StructuredPreview,
  CsvPreview,
  JsonlPreview,
  ParquetPreview,
} from "../../shared/api/contracts";
export type WorkspaceEntryKind = WorkspaceEntry["kind"];
export type WorkspacePreview =
  | UnsupportedPreview
  | TextPreview
  | MarkdownPreview
  | StructuredPreview
  | CsvPreview
  | JsonlPreview
  | ParquetPreview;
export type WorkspacePreviewKind = WorkspacePreview["kind"];
