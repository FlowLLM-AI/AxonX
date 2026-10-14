import { parseQuality } from "./quality";
import type { TaskMetadata, TaskSummary } from "../tasks/types";
import type { ArtifactFile } from "../research/types";
import {
  parseStockReport,
  artifactPath,
  type StockOnlineReport,
} from "./report";

export interface OnlineOutcome {
  key: string;
  status: string;
  reason?: string;
  elapsed_seconds?: number;
  rows?: number;
  coverage?: number | null;
  metrics?: Record<string, unknown>;
  artifacts?: Record<string, ArtifactFile>;
}
export interface OnlineReport {
  windows?: OnlineOutcome[];
  comparisons?: OnlineOutcome[];
  model_identity?: Record<string, string>;
  report?: StockOnlineReport | null;
  artifacts?: Record<string, ArtifactFile>;
}
export const isOnlineTask = (task: TaskMetadata | TaskSummary) =>
  !("output_params" in task)
    ? task.is_online === true
    : task.task_type === "api" ||
      task.task_type === "inference" ||
      (task.task_type === "analysis" &&
        (Array.isArray(task.output_params.comparisons) ||
          Array.isArray(task.input_params.comparison_keys)));

const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

export function parseOnlineReport(value: unknown): OnlineReport {
  if (!record(value)) throw new Error("Invalid online report");
  for (const key of ["windows", "comparisons"]) {
    if (value[key] === undefined) continue;
    if (
      !Array.isArray(value[key]) ||
      !value[key].every((row: unknown) => {
        if (
          !record(row) ||
          typeof row.key !== "string" ||
          typeof row.status !== "string"
        )
          return false;
        if (row.reason !== undefined && typeof row.reason !== "string")
          return false;
        if (row.metrics !== undefined && !record(row.metrics)) return false;
        if (record(row.metrics) && row.metrics.quality != null)
          parseQuality(row.metrics.quality);
        if (
          row.artifacts !== undefined &&
          (!record(row.artifacts) ||
            !Object.values(row.artifacts).every(artifactPath))
        )
          return false;
        return ["coverage", "rows", "elapsed_seconds"].every(
          (field) =>
            row[field] == null ||
            (typeof row[field] === "number" && Number.isFinite(row[field])),
        );
      })
    )
      throw new Error(`Invalid online report: ${key}`);
  }
  if (
    value.model_identity !== undefined &&
    (!record(value.model_identity) ||
      !Object.values(value.model_identity).every(
        (item) => typeof item === "string",
      ))
  )
    throw new Error("Invalid online report: model_identity");
  if (value.report != null) {
    parseStockReport(value.report);
    if (
      !record(value.artifacts) ||
      !artifactPath(value.artifacts.signal_history)
    )
      throw new Error("Missing online history artifact");
  }
  return value as OnlineReport;
}
