import { isArtifactRecord } from "../../shared/api/artifacts";
import { isRecord } from "../../shared/lib/values";
import type { ArtifactRecord } from "../../shared/api/contracts";
import type { TaskMetadata, TaskSummary } from "../tasks/types";
import { parseQuality } from "./quality";

import { parseStockReport, type StockOnlineReport } from "./report";

import type {
  WindowResult,
  PredictionComparison,
} from "../../shared/api/contracts";
export type OnlineOutcome = WindowResult | PredictionComparison;
export interface OnlineReport {
  windows?: WindowResult[];
  comparisons?: PredictionComparison[];
  model_identity?: Record<string, string>;
  report?: StockOnlineReport | null;
  artifacts?: Record<string, ArtifactRecord>;
}
export const isOnlineTask = (task: TaskMetadata | TaskSummary) =>
  ["online", "online_pipeline"].includes(task.report_kind || "");

export function parseOnlineReport(value: unknown): OnlineReport {
  if (!isRecord(value)) throw new Error("Invalid online report");
  for (const key of ["windows", "comparisons"]) {
    if (value[key] === undefined) continue;
    if (
      !Array.isArray(value[key]) ||
      !value[key].every((row: unknown) => {
        if (
          !isRecord(row) ||
          typeof row.key !== "string" ||
          typeof row.status !== "string" ||
          !(
            key === "windows"
              ? ["done", "skipped", "incomplete", "failed"]
              : [
                  "consistent",
                  "different",
                  "protocol_mismatch",
                  "missing",
                  "error",
                ]
          ).includes(row.status)
        )
          return false;
        if (row.reason !== undefined && typeof row.reason !== "string")
          return false;
        if (row.metrics !== undefined && !isRecord(row.metrics)) return false;
        if (isRecord(row.metrics) && row.metrics.quality != null)
          parseQuality(row.metrics.quality);
        if (
          row.artifacts !== undefined &&
          (!isRecord(row.artifacts) ||
            !Object.values(row.artifacts).every(isArtifactRecord))
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
    (!isRecord(value.model_identity) ||
      !Object.values(value.model_identity).every(
        (item) => typeof item === "string",
      ))
  )
    throw new Error("Invalid online report: model_identity");
  if (value.report != null) {
    parseStockReport(value.report);
    if (
      !isRecord(value.artifacts) ||
      !isArtifactRecord(value.artifacts.signal_history)
    )
      throw new Error("Missing online history artifact");
  }
  return value as OnlineReport;
}

export const hasTaskReport = (task: TaskMetadata) =>
  ["online", "online_pipeline", "compare_pipeline"].includes(
    task.report_kind || "",
  );
