import { isRecord } from "../../shared/lib/values";

export interface SignalRow extends Record<string, unknown> {
  trade_date: string;
  trade_time: string;
  ts_code: string;
  pred: number;
  target_rank: number | null;
  is_portfolio_candidate: boolean;
}

/** Reconstruct the cross section from source predictions and frozen deltas. */
export function restorePortfolioSignals(
  predictions: Record<string, unknown>[],
  rankings: Record<string, unknown>[],
  scoreColumn: string,
  scores: Record<string, unknown>[] | null = null,
): SignalRow[] {
  const key = (row: Record<string, unknown>) =>
    JSON.stringify([row.trade_date, row.trade_time, row.ts_code].map(String));
  const ranks = new Map(rankings.map((row) => [key(row), row.target_rank]));
  const values = scores && new Map(scores.map((row) => [key(row), row.pred]));
  const rows = predictions
    .map((row) => {
      const pred = values ? values.get(key(row)) : row[scoreColumn];
      if (typeof pred !== "number" || !Number.isFinite(pred))
        throw new Error("Missing final portfolio score");
      const target_rank = ranks.get(key(row)) ?? null;
      return {
        ...row,
        trade_date: String(row.trade_date),
        trade_time: String(row.trade_time),
        ts_code: String(row.ts_code),
        pred,
        target_rank,
        is_portfolio_candidate: target_rank !== null,
      } as SignalRow;
    })
    .sort(
      (a, b) =>
        a.trade_date.localeCompare(b.trade_date) ||
        a.trade_time.localeCompare(b.trade_time) ||
        b.pred - a.pred ||
        a.ts_code.localeCompare(b.ts_code),
    );
  let group = "",
    rank = 0,
    buyable = 0;
  return rows.map((row) => {
    const next = JSON.stringify([row.trade_date, row.trade_time]);
    if (next !== group) {
      group = next;
      rank = buyable = 0;
    }
    return {
      ...row,
      rank: ++rank,
      buyable_rank: row.is_buyable_at_signal ? ++buyable : null,
    };
  });
}

export function valueKey(value: unknown): string {
  return (
    JSON.stringify(value, (_key, item) =>
      isRecord(item)
        ? Object.fromEntries(
            Object.entries(item).sort(([a], [b]) => a.localeCompare(b)),
          )
        : item,
    ) ?? "undefined"
  );
}

export function portfolioValueLabel(value: unknown): string {
  if (Array.isArray(value))
    return `[${value.map(portfolioValueLabel).join(", ")}]`;
  if (isRecord(value))
    return (
      Object.entries(value)
        .map(([key, item]) =>
          ["kind", "method"].includes(key)
            ? portfolioValueLabel(item)
            : `${key}: ${portfolioValueLabel(item)}`,
        )
        .join(" · ") || "{}"
    );
  return value === "" ? '""' : String(value);
}

/** Cascade by identity key; each choice resolves to an existing portfolio. */
export function portfolioFields(
  identities: Record<string, unknown>[],
  selected: number,
) {
  const current = identities[selected] || identities[0];
  if (!current) return [];
  const keys = [...new Set(identities.flatMap(Object.keys))];
  return keys.map((key, position) => {
    const options = new Map<
      string,
      { value: unknown; index: number; matches: number }
    >();
    identities.forEach((identity, index) => {
      if (
        !keys
          .slice(0, position)
          .every(
            (before) =>
              valueKey(identity[before]) === valueKey(current[before]),
          )
      )
        return;
      const token = valueKey(identity[key]);
      const matches = keys
        .slice(position + 1)
        .filter(
          (after) => valueKey(identity[after]) === valueKey(current[after]),
        ).length;
      if (!options.has(token) || matches > options.get(token)!.matches)
        options.set(token, { value: identity[key], index, matches });
    });
    return { key, value: valueKey(current[key]), options };
  });
}
