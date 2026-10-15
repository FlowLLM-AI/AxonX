import { isRecord } from "../../shared/lib/values";

interface QualityCheck {
  stage: string;
  reason: string;
  action: string;
  input_count: number;
  output_count: number;
  matched_count: number;
  removed_count: number;
  threshold?: number;
  coverage?: number | null;
  samples: Record<string, unknown>[];
}
export interface QualitySummary {
  version: 1;
  trade_date: string;
  trade_time: string;
  checks: QualityCheck[];
}
export function parseQuality(value: unknown): QualitySummary {
  if (
    !isRecord(value) ||
    value.version !== 1 ||
    typeof value.trade_date !== "string" ||
    typeof value.trade_time !== "string" ||
    !Array.isArray(value.checks) ||
    !value.checks.every(
      (check) =>
        isRecord(check) &&
        ["stage", "reason", "action"].every(
          (key) => typeof check[key] === "string",
        ) &&
        ["input_count", "output_count", "matched_count", "removed_count"].every(
          (key) =>
            typeof check[key] === "number" &&
            Number.isInteger(check[key]) &&
            check[key] >= 0,
        ) &&
        ["threshold", "coverage"].every(
          (key) =>
            check[key] == null ||
            (typeof check[key] === "number" &&
              Number.isFinite(check[key]) &&
              check[key] >= 0 &&
              check[key] <= 1),
        ) &&
        Array.isArray(check.samples) &&
        check.samples.every(isRecord),
    )
  )
    throw new Error("Invalid quality summary");
  return value as unknown as QualitySummary;
}
