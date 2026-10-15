import { isArtifactRecord } from "../../shared/api/artifacts";
import { taskDirectory } from "../../shared/lib/tasks";
import type { ArtifactRecord } from "../../shared/api/contracts";
import { loadParquetRows } from "../workspace/parquet";

import { previewWorkspaceFile } from "../workspace/api";
import { parseQuality } from "./quality";
import { parseHistory, type OnlineCommit } from "./report";

export async function loadHistory(
  taskId: string,
  target?: string,
  signal?: AbortSignal,
) {
  const preview = await previewWorkspaceFile(
    `${taskDirectory(taskId)}/persistent/online/manifest.json`,
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
  if (!isArtifactRecord(artifact))
    throw new Error(`Missing online artifact: ${role}`);
  return loadArtifactRows(commit.task_id, artifact, target, signal);
}
export async function loadArtifactRows(
  taskId: string,
  artifact: ArtifactRecord,
  target?: string,
  signal?: AbortSignal,
) {
  if (!isArtifactRecord(artifact)) throw new Error("Invalid online artifact");
  return loadParquetRows(
    `${taskDirectory(taskId)}/${artifact.path}`,
    target,
    signal,
  );
}

export async function loadQuality(
  commit: OnlineCommit,
  target?: string,
  signal?: AbortSignal,
) {
  const artifact = commit.artifacts.quality_summary;
  if (!artifact) return null;
  if (!isArtifactRecord(artifact)) throw new Error("Invalid quality artifact");
  const preview = await previewWorkspaceFile(
    `${taskDirectory(commit.task_id)}/${artifact.path}`,
    0,
    1,
    target,
    signal,
  );
  signal?.throwIfAborted();
  if (preview.kind !== "json" || preview.parse_error || preview.truncated)
    throw new Error("Invalid quality file");
  return parseQuality(preview.data);
}
