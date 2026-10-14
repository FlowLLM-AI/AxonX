export type ReportTab =
  "signal" | "portfolio" | "performance" | "history" | "runtime" | "quality";

import type { ArtifactFile } from "../research/types";
import type { BenchmarkDefinition } from "../research/backtest/types";

export interface OnlineCommit {
  commit_id: string;
  task_id: string;
  run_id: string;
  trade_date: string;
  trade_time: string;
  revision: number;
  committed_at: string;
  model_identity: Record<string, string>;
  protocol: Record<string, unknown> & { report: ReportSettings };
  artifacts: Record<string, ArtifactFile>;
}
export interface ReportSettings {
  signals_format: "stock-signals-v1";
  strategy_identity: string;
  dimensions: {
    top_ns: number[];
    benchmarks: BenchmarkDefinition[];
    holding_detail_top_n: number;
  };
  date_range: { start: string; end: string };
  portfolio: Record<string, unknown>;
  score_selection: Record<string, unknown>;
  evaluation_status: "done" | "incomplete_market_data";
  missing_dates: string[];
}
export interface StockOnlineReport extends ReportSettings {
  kind: "stock_online";
  commit: OnlineCommit;
}
export interface OnlineHistory {
  version: 1;
  task_type: "inference";
  kind: "online_history";
  strategy_identity: string;
  commits: OnlineCommit[];
}
export const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const strings = (value: unknown): value is Record<string, string> =>
  record(value) &&
  Object.values(value).every((item) => typeof item === "string");
const digest = (value: unknown) =>
  typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
export function artifactPath(value: unknown): value is ArtifactFile {
  return (
    record(value) &&
    typeof value.path === "string" &&
    !!value.path &&
    !value.path.startsWith("/") &&
    !value.path.includes("\\") &&
    !value.path.split("/").some((part) => ["..", ".", ""].includes(part)) &&
    typeof value.size === "number" &&
    Number.isInteger(value.size) &&
    value.size >= 0 &&
    digest(value.sha256)
  );
}
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
const canonical = (value: unknown): string =>
  JSON.stringify(value, (_key, item) =>
    record(item)
      ? Object.fromEntries(
          Object.entries(item).sort(([a], [b]) => a.localeCompare(b)),
        )
      : item,
  );
function settings(value: unknown): value is ReportSettings {
  if (!record(value) || !record(value.dimensions) || !record(value.date_range))
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
        record(b) && typeof b.key === "string" && typeof b.label === "string",
    ) &&
    validDate(start) &&
    validDate(end) &&
    start <= end &&
    record(value.portfolio) &&
    record(value.score_selection) &&
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
    !record(value) ||
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
    !record(value.protocol) ||
    value.protocol.version !== 1 ||
    value.protocol.task_type !== "inference" ||
    !settings(value.protocol.report) ||
    !record(value.artifacts) ||
    !Object.values(value.artifacts).every(artifactPath)
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
  if (!record(value) || value.kind !== "stock_online" || !settings(value))
    throw new Error("Invalid stock online report");
  const commit = parseCommit(value.commit);
  if (
    value.date_range.end !== commit.trade_date ||
    value.strategy_identity !== commit.protocol.report.strategy_identity
  )
    throw new Error("Invalid stock online report scope");
  const reportSettings = Object.fromEntries(
    Object.entries(value).filter(([key]) => !["kind", "commit"].includes(key)),
  );
  if (canonical(reportSettings) !== canonical(commit.protocol.report))
    throw new Error("Online report settings differ from its commit");
  return { ...(value as unknown as StockOnlineReport), commit };
}
export function parseHistory(value: unknown): OnlineHistory {
  if (
    !record(value) ||
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
