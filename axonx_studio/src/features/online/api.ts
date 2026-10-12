import { previewWorkspaceFile } from "../workspace/api";
import { artifactPath, parseHistory, type OnlineCommit } from "./report";

export const taskRoot = (taskId: string) => `${taskId.split("#")[0]}/${taskId}`;
export async function loadHistory(
  taskId: string,
  target?: string,
  signal?: AbortSignal,
) {
  const preview = await previewWorkspaceFile(
    `${taskRoot(taskId)}/persistent/online/manifest.json`,
    0,
    1,
    target,
    signal,
  );
  signal?.throwIfAborted();
  if (preview.kind !== "json" || preview.parse_error || preview.truncated)
    throw new Error("Invalid online history file");
  const history = parseHistory(preview.data);
  if (history.commits.some((commit) => commit.task_id !== taskId))
    throw new Error("Online history belongs to another Task");
  return history;
}
export async function loadRows(
  commit: OnlineCommit,
  role: string,
  target?: string,
  signal?: AbortSignal,
) {
  const artifact = commit.artifacts[role];
  if (!artifactPath(artifact))
    throw new Error(`Missing online artifact: ${role}`);
  const rows: Record<string, unknown>[] = [];
  for (let offset = 0; ; offset += 5000) {
    const preview = await previewWorkspaceFile(
      `${taskRoot(commit.task_id)}/${artifact.path}`,
      offset,
      5000,
      target,
      signal,
    );
    signal?.throwIfAborted();
    if (preview.kind !== "parquet")
      throw new Error(`Expected Parquet: ${role}`);
    rows.push(
      ...preview.rows.map((row) =>
        Object.fromEntries(
          preview.columns.map((column, index) => [column, row[index]]),
        ),
      ),
    );
    if (!preview.has_more) return rows;
  }
}
