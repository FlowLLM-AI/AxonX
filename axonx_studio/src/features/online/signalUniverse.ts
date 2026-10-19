/** Display filters over recorded signal-time context, matching stock universe definitions. */
export type SignalRow = Record<string, unknown>;
export interface SignalUniverse {
  key: string;
  kind: "all" | "index" | "percentile";
  index_codes?: string[];
  field?: string;
  top_percent?: number;
}

export function parseUniverse(value: unknown): SignalUniverse | null {
  if (value == null) return { key: "all", kind: "all" };
  if (typeof value !== "object") return null;
  const p = value as Record<string, unknown>;
  if (p.kind === "all") return { key: "all", kind: "all" };
  if (
    p.kind === "index" &&
    Array.isArray(p.index_codes) &&
    p.index_codes.length &&
    p.index_codes.every((c) => ["hs300", "zz500", "zz1000"].includes(String(c)))
  ) {
    return {
      key: p.index_codes.join("_"),
      kind: "index",
      index_codes: p.index_codes as string[],
    };
  }
  if (
    p.kind === "percentile" &&
    ["estimated_total_market_cap", "amount_to_signal"].includes(
      String(p.field),
    ) &&
    Number.isInteger(p.top_percent) &&
    Number(p.top_percent) >= 1 &&
    Number(p.top_percent) <= 100
  ) {
    return {
      key: `${p.field}_top_${p.top_percent}`,
      kind: "percentile",
      field: String(p.field),
      top_percent: Number(p.top_percent),
    };
  }
  return null;
}

export const signalUniverses: SignalUniverse[] = [
  { key: "all", kind: "all" },
  ...[["hs300"], ["hs300", "zz500"], ["hs300", "zz500", "zz1000"]].map(
    (index_codes) => ({
      key: index_codes.join("_"),
      kind: "index" as const,
      index_codes,
    }),
  ),
  ...["estimated_total_market_cap", "amount_to_signal"].flatMap((field) =>
    Array.from({ length: 9 }, (_, i) => ({
      key: `${field}_top_${(i + 1) * 10}`,
      kind: "percentile" as const,
      field,
      top_percent: (i + 1) * 10,
    })),
  ),
];

export function missingUniverseContext(
  rows: SignalRow[],
  pool: SignalUniverse,
) {
  const fields =
    pool.kind === "index"
      ? pool.index_codes!.map((c) => `index_weight_${c}`)
      : pool.kind === "percentile"
        ? [pool.field!]
        : [];
  return fields.some((field) => rows.some((row) => !(field in row)));
}

export function filterSignalUniverse(
  rows: SignalRow[],
  pool: SignalUniverse,
  buyableOnly: boolean,
) {
  const candidates = rows.filter((row) => row.is_model_candidate !== false);
  const eligible = candidates.filter(
    (row) => row.is_buyable_at_signal === true,
  );
  let selected = buyableOnly ? eligible : candidates;
  if (pool.kind === "index") {
    selected = selected.filter((row) =>
      pool.index_codes!.some(
        (code) =>
          typeof row[`index_weight_${code}`] === "number" &&
          Number(row[`index_weight_${code}`]) > 0,
      ),
    );
  } else if (pool.kind === "percentile") {
    // Boundaries always use eligible stocks, even when blocked stocks are shown for inspection.
    const valid = (row: SignalRow) =>
      typeof row[pool.field!] === "number" &&
      Number.isFinite(row[pool.field!] as number) &&
      Number(row[pool.field!]) > 0;
    const groups = new Map<string, SignalRow[]>();
    for (const row of eligible.filter(valid)) {
      const key = `${row.trade_date}:${row.trade_time}`;
      const group = groups.get(key) || [];
      group.push(row);
      groups.set(key, group);
    }
    const keys = new Set<SignalRow>();
    for (const group of groups.values()) {
      group.sort(
        (a, b) =>
          Number(b[pool.field!]) - Number(a[pool.field!]) ||
          String(a.ts_code).localeCompare(String(b.ts_code)),
      );
      group
        .slice(0, Math.ceil((group.length * pool.top_percent!) / 100))
        .forEach((row) => keys.add(row));
    }
    selected = selected.filter((row) => keys.has(row));
  }
  return selected.sort(
    (a, b) =>
      Number(b.pred) - Number(a.pred) ||
      String(a.ts_code).localeCompare(String(b.ts_code)),
  );
}
