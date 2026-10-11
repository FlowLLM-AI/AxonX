import { listWorkspaceEntries, previewWorkspaceFile } from "../workspace/api";
import type { TaskMetadata } from "../tasks/types";
import { parseOnlineReport, type OnlineReport } from "./types";

async function findEntry(
  path: string,
  name: string,
  target: string | undefined,
  signal: AbortSignal,
) {
  let offset = 0;
  while (!signal.aborted) {
    const page = await listWorkspaceEntries(path, target, signal, offset);
    const entry = page.entries.find((entry) => entry.name === name);
    if (entry) return entry;
    if (!page.truncated || !page.entries.length) return undefined;
    offset += page.entries.length;
  }
  signal.throwIfAborted();
}

export async function loadOnlineReport(
  task: TaskMetadata,
  target: string | undefined,
  signal: AbortSignal,
): Promise<OnlineReport> {
  if (task.output_params.windows || task.output_params.comparisons)
    return parseOnlineReport(task.output_params);
  // Running tasks may publish business reports before preparing their final output.
  const entry = await findEntry(task.task_type, task.task_id, target, signal);
  if (!entry) return {};
  const filename =
    task.task_type === "analysis" ? "comparison.json" : "manifest.json";
  const manifest = await findEntry(entry.path, filename, target, signal);
  if (!manifest) return {};
  const preview = await previewWorkspaceFile(
    manifest.path,
    0,
    200,
    target,
    signal,
  );
  if (
    preview.kind !== "json" ||
    preview.truncated ||
    preview.parse_error ||
    !preview.data ||
    typeof preview.data !== "object" ||
    Array.isArray(preview.data)
  ) {
    throw new Error(`Invalid online report: ${manifest.path}`);
  }
  return parseOnlineReport(preview.data);
}
