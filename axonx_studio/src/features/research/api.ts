import { displayArtifacts, loadArtifactRows } from "../../shared/api/artifacts";
import { axonx, type RequestOptions } from "../../shared/api/client";
import type { TaskMetadata, TaskSummary } from "../../shared/api/contracts";
import { loadParquetRows, readJsonFile } from "../../shared/api/tables";
import { taskDirectory } from "../../shared/lib/tasks";
import { restorePortfolioSignals, valueKey } from "./portfolio";
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

export async function loadPortfolioSignals(
  meta: ResearchTask<"portfolio">,
  index: number,
  options: RequestOptions = {},
) {
  const output = meta.output_params;
  const plan = output.portfolios[index];
  const universe = output.universes.find(
    (u) => valueKey(u.parameters) === valueKey(plan.portfolio_id.universe),
  );
  if (!universe) throw new Error("Missing portfolio universe");
  const predictions = async () => {
    if (typeof meta.input_params.input_file === "string")
      return loadParquetRows(meta.input_params.input_file, options);
    const source = Object.entries(meta.input_sources).find(([id]) =>
      id.startsWith("predict#"),
    );
    if (!source) throw new Error("Missing prediction source");
    const [id, expected] = source;
    const raw = (await readJsonFile(
      `${taskDirectory(id)}/metadata.json`,
      options,
    )) as TaskMetadata;
    const actual = (
      raw.output_params.artifacts as Record<
        string,
        import("../../shared/api/contracts").ArtifactRecord
      >
    ).predictions;
    const pinned = expected.artifacts.predictions;
    if (
      raw.task_id !== id ||
      raw.state !== "succeeded" ||
      Date.parse(raw.started_at) !== Date.parse(expected.started_at) ||
      !actual ||
      !pinned ||
      actual.path !== pinned.path ||
      actual.size !== pinned.size ||
      actual.revision !== pinned.revision
    )
      throw new Error("Prediction source changed since portfolio construction");
    return loadArtifactRows(id, displayArtifacts(raw).predictions, options);
  };
  const [raw, ranks, scores] = await Promise.all([
    predictions(),
    loadArtifactRows(
      meta.task_id,
      output.artifacts[plan.artifacts.rankings],
      options,
    ),
    plan.artifacts.scores
      ? loadArtifactRows(
          meta.task_id,
          output.artifacts[plan.artifacts.scores],
          options,
        )
      : Promise.resolve(null),
  ]);
  return restorePortfolioSignals(
    raw,
    ranks.filter((row) => row.universe_key === universe.key),
    output.score_column,
    scores,
  );
}
