import { displayArtifacts, loadJsonArtifact } from "../../shared/api/artifacts";
import { axonx, type RequestOptions } from "../../shared/api/client";
import type { TaskMetadata, TaskSummary } from "../../shared/api/contracts";
import { isRecord } from "../../shared/lib/values";
import { getTaskStatus } from "../tasks/api";
import type { ResearchKind, ResearchTask } from "./types";

export async function listResearchTasks(
  kind: ResearchKind,
  options: RequestOptions = {},
): Promise<TaskSummary[]> {
  const records = await axonx.invoke<TaskSummary[]>(
    "list_task_statuses",
    { detail: "summary", task_type: kind, state: "succeeded" },
    options,
  );
  options.signal?.throwIfAborted();
  return records;
}

export async function getResearchTask<K extends ResearchKind>(
  kind: K,
  taskId: string,
  options: RequestOptions = {},
): Promise<ResearchTask<K>> {
  const metadata: TaskMetadata = await getTaskStatus(taskId, options);
  options.signal?.throwIfAborted();
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
  ) as ResearchTask<K>;
}

export async function countTrainingMembers(
  meta: ResearchTask<"train">,
  options: RequestOptions = {},
): Promise<number | null> {
  const artifact = meta.output_params.artifacts.model_manifest;
  // A display replica may intentionally omit the model collection.
  if (!artifact) return null;
  const data = await loadJsonArtifact(meta.task_id, artifact, options);
  if (
    !isRecord(data) ||
    data.version !== 1 ||
    data.task_type !== "train" ||
    !isRecord(data.members)
  )
    throw new Error("Invalid model collection");
  const members = Object.values(data.members);
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
