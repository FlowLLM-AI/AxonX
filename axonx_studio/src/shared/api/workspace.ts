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
    allow_missing = false,
  }: { path: string; offset?: number; limit?: number; allow_missing?: boolean },
  options: RequestOptions = {},
) =>
  axonx.invoke<WorkspacePreview | null>(
    "preview_file",
    { path, offset, limit, ...(allow_missing ? { allow_missing: true } : {}) },
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

export interface WorkspaceText {
  content: string;
  truncated: boolean;
}

/** Read the original UTF-8 prefix; Markdown previews omit the source frontmatter. */
export async function readWorkspaceText(
  { path, workspaceRoot }: { path: string; workspaceRoot: string },
  options: RequestOptions = {},
): Promise<WorkspaceText> {
  const settings = JSON.stringify([workspaceRoot, path, 512 * 1024]);
  const code = `# axonx:workspace-text
import base64, json
from axonx.app.workspace.core import Workspace
settings = json.loads(${JSON.stringify(settings)})
root, path, limit = settings
try:
    with Workspace(root).resolve_file(path).open("rb") as handle:
        data = handle.read(limit + 1)
    print(json.dumps({"data": base64.b64encode(data[:limit]).decode("ascii"), "truncated": len(data) > limit}))
except (OSError, ValueError) as error:
    print(json.dumps({"error": str(error)}))`;
  const output = await axonx.invoke<{
    stdout: string;
    stdout_truncated: boolean;
  }>("python", { code, timeout: 15 }, options);
  if (output.stdout_truncated)
    throw new Error("Raw file response was truncated");
  const source: unknown = JSON.parse(output.stdout);
  if (
    source &&
    typeof source === "object" &&
    "error" in source &&
    typeof source.error === "string"
  )
    throw new Error(source.error);
  if (
    !source ||
    typeof source !== "object" ||
    !("data" in source) ||
    typeof source.data !== "string" ||
    !("truncated" in source) ||
    typeof source.truncated !== "boolean"
  )
    throw new Error("Invalid raw file response");
  const bytes = Uint8Array.from(atob(source.data), (value) =>
    value.charCodeAt(0),
  );
  return {
    content: new TextDecoder("utf-8", { fatal: true }).decode(bytes, {
      stream: source.truncated,
    }),
    truncated: source.truncated,
  };
}
