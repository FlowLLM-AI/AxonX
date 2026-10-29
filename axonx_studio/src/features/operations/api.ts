import { loadJsonArtifact } from "../../shared/api/artifacts";
import type { RequestOptions } from "../../shared/api/client";
import { readJsonFile } from "../../shared/api/tables";
import { taskDirectory } from "../../shared/lib/tasks";
import { isRecord } from "../../shared/lib/values";
import {
  parseHistory,
  parseHistoryNode,
  parseQuality,
  type OnlineCommit,
} from "./report";

export async function loadHistory(
  taskId: string,
  options: RequestOptions = {},
) {
  let value = await readJsonFile(
    `${taskDirectory(taskId)}/persistent/online/manifest.json`,
    options,
  );
  const blocks: OnlineCommit[][] = [];
  const visited = new Set<string>();
  let strategy: string | undefined;
  while (isRecord(value) && value.kind === "online_history_node") {
    const node = parseHistoryNode(value);
    if (strategy !== undefined && node.strategy_identity !== strategy)
      throw new Error("Online history strategy changed");
    strategy = node.strategy_identity;
    blocks.push(node.commits);
    if (!node.previous) {
      value = {
        version: 1,
        task_type: "inference",
        kind: "online_history",
        strategy_identity: strategy,
        commits: [],
      };
      break;
    }
    if (visited.has(node.previous.path))
      throw new Error("Cyclic online history");
    visited.add(node.previous.path);
    value = await loadJsonArtifact(taskId, node.previous, options);
  }
  const base = parseHistory(value);
  if (strategy !== undefined && base.strategy_identity !== strategy)
    throw new Error("Online history strategy changed");
  const history = parseHistory({
    ...base,
    commits: [...base.commits, ...blocks.reverse().flat()],
  });
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
