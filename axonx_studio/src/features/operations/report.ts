import { isArtifactRecord } from "../../shared/api/artifacts";
import type {
  ArtifactRecord,
  OnlineCommit as CommitContract,
  OnlineHistory as HistoryContract,
  PredictionComparison,
  StockOnlineReport as ReportContract,
  StockReportSettings,
  WindowResult,
} from "../../shared/api/contracts";
import { isRecord } from "../../shared/lib/values";

export type ReportTab =
  "signal" | "portfolio" | "performance" | "history" | "runtime";

export type ReportSettings = StockReportSettings;
export type OnlineCommit = Omit<CommitContract, "protocol"> & {
  protocol: Record<string, unknown> & { report: ReportSettings };
};
export type StockOnlineReport = Omit<ReportContract, "commit"> & {
  commit: OnlineCommit;
};
export type OnlineHistory = Omit<HistoryContract, "commits"> & {
  commits: OnlineCommit[];
};
export type OnlineHistoryNode = Omit<OnlineHistory, "kind"> & {
  kind: "online_history_node";
  previous: ArtifactRecord | null;
};
const strings = (value: unknown): value is Record<string, string> =>
  isRecord(value) &&
  Object.values(value).every((item) => typeof item === "string");
const digest = (value: unknown) =>
  typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const validDate = (value: unknown): value is string => {
  if (typeof value !== "string" || !/^\d{8}$/.test(value)) return false;
  const date = new Date(
    `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}T00:00:00Z`,
  );
  return (
    Number.isFinite(date.getTime()) &&
    date.toISOString().slice(0, 10).replaceAll("-", "") === value
  );
};
function settings(value: unknown): value is ReportSettings {
  if (
    !isRecord(value) ||
    !isRecord(value.dimensions) ||
    !isRecord(value.date_range)
  )
    return false;
  const { top_ns, benchmarks, holding_detail_top_n } = value.dimensions;
  const { start, end } = value.date_range;
  return (
    value.signals_format === "stock-signals-v1" &&
    digest(value.strategy_identity) &&
    Array.isArray(top_ns) &&
    top_ns.length > 0 &&
    new Set(top_ns).size === top_ns.length &&
    top_ns.every((n) => Number.isInteger(n) && n > 0) &&
    typeof holding_detail_top_n === "number" &&
    Number.isInteger(holding_detail_top_n) &&
    holding_detail_top_n > 0 &&
    Array.isArray(benchmarks) &&
    benchmarks.every(
      (b) =>
        isRecord(b) && typeof b.key === "string" && typeof b.label === "string",
    ) &&
    validDate(start) &&
    validDate(end) &&
    start <= end &&
    isRecord(value.portfolio) &&
    isRecord(value.score_selection) &&
    ["done", "incomplete_market_data"].includes(
      String(value.evaluation_status),
    ) &&
    Array.isArray(value.missing_dates) &&
    value.missing_dates.every(
      (d) => validDate(d) && d >= String(start) && d <= String(end),
    )
  );
}
function parseCommit(value: unknown): OnlineCommit {
  if (
    !isRecord(value) ||
    typeof value.commit_id !== "string" ||
    !/^[a-f0-9]{32}$/.test(value.commit_id) ||
    typeof value.task_id !== "string" ||
    !value.task_id ||
    typeof value.started_at !== "string" ||
    !Number.isFinite(Date.parse(value.started_at)) ||
    !validDate(value.trade_date) ||
    typeof value.trade_time !== "string" ||
    !/^(?:[01]\d|2[0-3])[0-5]\d$/.test(value.trade_time) ||
    typeof value.revision !== "number" ||
    !Number.isInteger(value.revision) ||
    value.revision < 1 ||
    typeof value.committed_at !== "string" ||
    !Number.isFinite(Date.parse(value.committed_at)) ||
    !strings(value.model_identity) ||
    Object.keys(value.model_identity).length === 0 ||
    !isRecord(value.protocol) ||
    value.protocol.version !== 1 ||
    value.protocol.task_type !== "inference" ||
    !settings(value.protocol.report) ||
    !isRecord(value.artifacts) ||
    !Object.values(value.artifacts).every(isArtifactRecord)
  )
    throw new Error("Invalid online commit");
  for (const role of [
    "signal",
    "signals",
    "predictions",
    "market",
    "daily",
    "summary",
    "positions",
    "orders",
    "trades",
    "prediction_protocol",
    "calendar",
    "input_features",
  ])
    if (!value.artifacts[role])
      throw new Error(`Missing online artifact: ${role}`);
  if (value.protocol.report.date_range.end !== value.trade_date)
    throw new Error("Invalid online report cutoff");
  return value as unknown as OnlineCommit;
}
export function parseStockReport(value: unknown): StockOnlineReport {
  if (
    !isRecord(value) ||
    value.kind !== "stock_online" ||
    Object.keys(value).some((key) => !["kind", "commit"].includes(key))
  )
    throw new Error("Invalid stock online report");
  return { kind: "stock_online", commit: parseCommit(value.commit) };
}
export function parseHistory(value: unknown): OnlineHistory {
  if (
    !isRecord(value) ||
    value.version !== 1 ||
    value.task_type !== "inference" ||
    value.kind !== "online_history" ||
    !digest(value.strategy_identity) ||
    !Array.isArray(value.commits)
  )
    throw new Error("Invalid online history");
  const commits = value.commits.map(parseCommit);
  const ids = new Set<string>();
  const revisions = new Map<string, number>();
  for (const commit of commits) {
    const key = `${commit.trade_date}/${commit.trade_time}`;
    const revision = (revisions.get(key) || 0) + 1;
    if (
      (commits.length > 0 && commit.task_id !== commits[0].task_id) ||
      ids.has(commit.commit_id) ||
      commit.revision !== revision ||
      commit.protocol.report.strategy_identity !== value.strategy_identity
    )
      throw new Error("Invalid online revisions");
    ids.add(commit.commit_id);
    revisions.set(key, revision);
  }
  return { ...(value as unknown as OnlineHistory), commits };
}
export function parseHistoryNode(value: unknown): OnlineHistoryNode {
  if (
    !isRecord(value) ||
    value.version !== 1 ||
    value.task_type !== "inference" ||
    value.kind !== "online_history_node" ||
    !digest(value.strategy_identity) ||
    !Array.isArray(value.commits) ||
    value.commits.length < 1 ||
    value.commits.length > 16 ||
    (value.previous != null &&
      (!isArtifactRecord(value.previous) ||
        !/^persistent\/online\/commits\/[a-f0-9]{32}\/history\.json$/.test(
          value.previous.path,
        )))
  )
    throw new Error("Invalid online history node");
  return {
    ...(value as unknown as OnlineHistoryNode),
    commits: value.commits.map(parseCommit),
    previous: (value.previous as ArtifactRecord | null) ?? null,
  };
}
export function activeCommits(history: OnlineHistory) {
  const latest = new Map(
    history.commits.map((commit) => [
      `${commit.trade_date}/${commit.trade_time}`,
      commit,
    ]),
  );
  return [...latest.values()].sort((a, b) =>
    `${a.trade_date}${a.trade_time}`.localeCompare(
      `${b.trade_date}${b.trade_time}`,
    ),
  );
}
export function reportIsCurrent(history: OnlineHistory, commit: OnlineCommit) {
  const index = history.commits.findIndex(
    (item) => item.commit_id === commit.commit_id,
  );
  return (
    index >= 0 &&
    !history.commits
      .slice(index + 1)
      .some(
        (item) =>
          `${item.trade_date}${item.trade_time}` <=
          `${commit.trade_date}${commit.trade_time}`,
      )
  );
}

export type OnlineOutcome = WindowResult | PredictionComparison;
interface OnlineReport {
  windows?: WindowResult[];
  comparisons?: PredictionComparison[];
  model_identity?: Record<string, string>;
  report?: StockOnlineReport | null;
  artifacts?: Record<string, ArtifactRecord>;
}

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
