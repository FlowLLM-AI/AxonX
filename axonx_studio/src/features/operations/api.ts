import { loadJsonArtifact } from "../../shared/api/artifacts";
import type { RequestOptions } from "../../shared/api/client";
import { readJsonFile } from "../../shared/api/tables";
import { taskDirectory } from "../../shared/lib/tasks";
import { parseHistory, parseQuality, type OnlineCommit } from "./report";

export async function loadHistory(
  taskId: string,
  options: RequestOptions = {},
) {
  const history = parseHistory(
    await readJsonFile(
      `${taskDirectory(taskId)}/persistent/online/manifest.json`,
      options,
    ),
  );
  if (history.commits.some((commit) => commit.task_id !== taskId))
    throw new Error("Online history belongs to another Task");
  return history;
}
export async function loadQuality(
  commit: OnlineCommit,
  options: RequestOptions = {},
) {
  const artifact = commit.artifacts.quality_summary;
  return artifact
    ? parseQuality(await loadJsonArtifact(commit.task_id, artifact, options))
    : null;
}
