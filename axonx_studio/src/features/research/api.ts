import { axonx } from "../../shared/api/client";
import { previewWorkspaceFile } from "../workspace/api";
import { taskDirectory } from "../../shared/lib/tasks";
import { isRecord } from "../../shared/lib/values";
import { displayArtifacts } from "../../shared/lib/replica";
import { getTaskStatus } from "../tasks/api";
import type { TaskMetadata } from "../../shared/api/contracts";
import type { TaskSummary } from "../tasks/types";
import type { ResearchArtifact, ResearchKind } from "./types";

export async function listResearchTasks(
  kind: ResearchKind,
  target?: string,
  signal?: AbortSignal,
): Promise<TaskSummary[]> {
  const records = await axonx.invoke<TaskSummary[]>(
    "list_task_statuses",
    { detail: "summary", task_type: kind, state: "succeeded" },
    { target, signal },
  );
  signal?.throwIfAborted();
  return records;
}

export async function getResearchTask<K extends ResearchKind>(
  kind: K,
  taskId: string,
  target?: string,
  signal?: AbortSignal,
): Promise<ResearchArtifact<K>> {
  const metadata: TaskMetadata = await getTaskStatus(taskId, target, signal);
  signal?.throwIfAborted();
  if (
    metadata.task_id !== taskId ||
    metadata.task_type !== kind ||
    metadata.state !== "succeeded"
  )
    throw new Error("Research task changed; refresh the task list");
  return (
    metadata.replica
      ? {
          ...metadata,
          output_params: {
            ...metadata.output_params,
            artifacts: displayArtifacts(metadata),
          },
        }
      : metadata
  ) as ResearchArtifact<K>;
}

export async function countTrainingMembers(
  meta: ResearchArtifact<"train">,
  target?: string,
  signal?: AbortSignal,
): Promise<number | null> {
  const artifact = meta.output_params.artifacts.model_manifest;
  // A display replica may intentionally omit the model collection.
  if (!artifact) return null;
  const preview = await previewWorkspaceFile(
    `${taskDirectory(meta.task_id)}/${artifact.path}`,
    0,
    1,
    target,
    signal,
  );
  signal?.throwIfAborted();
  if (
    preview.kind !== "json" ||
    preview.parse_error ||
    preview.truncated ||
    !isRecord(preview.data) ||
    preview.data.version !== 1 ||
    preview.data.task_type !== "train" ||
    !isRecord(preview.data.members)
  )
    throw new Error("Invalid model collection");
  const members = Object.values(preview.data.members);
  if (
    !members.length ||
    !members.every(
      (member) =>
        isRecord(member) &&
        typeof member.model_artifact === "string" &&
        isRecord(member.model),
    )
  )
    throw new Error("Invalid model collection members");
  return members.length;
}
