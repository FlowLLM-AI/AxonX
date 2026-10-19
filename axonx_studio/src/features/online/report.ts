import { isRecord } from "../../shared/lib/values";
import { isArtifactRecord } from "../../shared/api/artifacts";
export type ReportTab =
  | "signal"
  | "portfolio"
  | "performance"
  | "history"
  | "runtime"
  | "quality"
  | "provenance";

import type {
  OnlineCommit as CommitContract,
  StockReportSettings,
  OnlineHistory as HistoryContract,
  StockOnlineReport as ReportContract,
} from "../../shared/api/contracts";
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
export function parseCommit(value: unknown): OnlineCommit {
  if (
    !isRecord(value) ||
    typeof value.commit_id !== "string" ||
    !/^[a-f0-9]{32}$/.test(value.commit_id) ||
    typeof value.task_id !== "string" ||
    !value.task_id ||
    typeof value.run_id !== "string" ||
    !value.run_id ||
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
