import { isRecord } from "../../shared/lib/values";

export const TOP_NS = [5, 10, 20, 30, 50] as const;
export interface TopStock {
  code: string;
  name: string | null;
  rank: number | null;
  score: number;
  std: number;
  seeds: Record<string, number>;
}
interface Snapshot {
  count: number;
  rows: TopStock[];
}
export interface TopComparisonData {
  version: 1;
  key: string;
  std_ddof: 0;
  mock_online?: boolean;
  absolute_tolerance: number;
  relative_tolerance: number;
  score_selection: { seed: number | null; aggregation: string };
  universe: Record<string, unknown>;
  scopes: Record<"buyable" | "all", Record<"online" | "offline", Snapshot>>;
}
const finite = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);
export function parseTopComparison(value: unknown): TopComparisonData {
  const fail = () => {
    throw new Error("Invalid Top N comparison artifact");
  };
  if (
    !isRecord(value) ||
    value.version !== 1 ||
    typeof value.key !== "string" ||
    value.std_ddof !== 0 ||
    !finite(value.absolute_tolerance) ||
    value.absolute_tolerance < 0 ||
    !finite(value.relative_tolerance) ||
    value.relative_tolerance < 0 ||
    !isRecord(value.scopes) ||
    !isRecord(value.universe) ||
    !isRecord(value.score_selection) ||
    !(
      value.score_selection.seed === null ||
      Number.isInteger(value.score_selection.seed)
    ) ||
    !["mean", "rank_mean"].includes(String(value.score_selection.aggregation))
  )
    return fail();
  const pool = value.universe;
  if (
    !["all", "index", "percentile"].includes(String(pool.kind)) ||
    (pool.kind === "index" &&
      (!Array.isArray(pool.index_codes) ||
        !pool.index_codes.length ||
        !pool.index_codes.every((c) =>
          ["hs300", "zz500", "zz1000"].includes(String(c)),
        ))) ||
    (pool.kind === "percentile" &&
      (!["estimated_total_market_cap", "amount_to_signal"].includes(
        String(pool.field),
      ) ||
        !Number.isInteger(pool.top_percent) ||
        Number(pool.top_percent) < 1 ||
        Number(pool.top_percent) > 100)) ||
    (value.mock_online !== undefined && typeof value.mock_online !== "boolean")
  )
    return fail();
  for (const scope of ["buyable", "all"]) {
    const group = value.scopes[scope];
    if (!isRecord(group)) return fail();
    for (const side of ["online", "offline"]) {
      const snapshot = group[side];
      if (
        !isRecord(snapshot) ||
        !Number.isInteger(snapshot.count) ||
        Number(snapshot.count) < 0 ||
        !Array.isArray(snapshot.rows) ||
        snapshot.rows.length > 100
      )
        return fail();
      const codes = new Set(),
        ranks = new Set();
      for (const row of snapshot.rows) {
        if (
          !isRecord(row) ||
          typeof row.code !== "string" ||
          !row.code ||
          !(row.name === null || typeof row.name === "string") ||
          (!(row.rank === null && scope === "buyable") &&
            (!Number.isInteger(row.rank) ||
              Number(row.rank) < 1 ||
              Number(row.rank) > Number(snapshot.count))) ||
          !finite(row.score) ||
          !finite(row.std) ||
          row.std < 0 ||
          !isRecord(row.seeds) ||
          !Object.keys(row.seeds).length ||
          !Object.values(row.seeds).every(finite) ||
          codes.has(row.code) ||
          (row.rank !== null && ranks.has(row.rank))
        )
          return fail();
        codes.add(row.code);
        if (row.rank !== null) ranks.add(row.rank);
      }
      // Every selectable rank must be present; counterparts may rank below Top 50.
      for (let rank = 1; rank <= Math.min(50, Number(snapshot.count)); rank++)
        if (!ranks.has(rank)) return fail();
    }
  }
  return value as unknown as TopComparisonData;
}
export function topRows(
  data: TopComparisonData,
  scope: "buyable" | "all",
  n: number,
) {
  const { online, offline } = data.scopes[scope];
  const on = new Map(online.rows.map((r) => [r.code, r])),
    off = new Map(offline.rows.map((r) => [r.code, r]));
  const codes = new Set(
    [...online.rows, ...offline.rows]
      .filter((r) => r.rank !== null && r.rank <= n)
      .map((r) => r.code),
  );
  const equal = (a: number, b: number) =>
    Math.abs(a - b) <=
    data.absolute_tolerance + data.relative_tolerance * Math.abs(a);
  return [...codes]
    .map((code) => {
      const a = on.get(code),
        b = off.get(code);
      const membership =
        a && a.rank !== null && a.rank <= n
          ? b && b.rank !== null && b.rank <= n
            ? "both"
            : "onlineOnly"
          : "offlineOnly";
      const different =
        !a ||
        !b ||
        membership !== "both" ||
        a.name !== b.name ||
        a.rank !== b.rank ||
        !equal(a.score, b.score) ||
        !equal(a.std, b.std) ||
        [...new Set([...Object.keys(a.seeds), ...Object.keys(b.seeds)])].some(
          (seed) =>
            a.seeds[seed] === undefined ||
            b.seeds[seed] === undefined ||
            !equal(a.seeds[seed], b.seeds[seed]),
        );
      return {
        code,
        name: a?.name || b?.name || "—",
        stock: `${code} ${a?.name || ""} ${b?.name || ""}`,
        rank: a?.rank ?? b?.rank,
        score: a?.score ?? b?.score,
        std: a?.std ?? b?.std,
        online: a,
        offline: b,
        membership,
        different,
        delta: a && b ? a.score - b.score : null,
      };
    })
    .sort(
      (a, b) =>
        (a.membership === "offlineOnly" ? Infinity : a.online!.rank!) -
          (b.membership === "offlineOnly" ? Infinity : b.online!.rank!) ||
        (a.offline?.rank || 0) - (b.offline?.rank || 0),
    );
}
