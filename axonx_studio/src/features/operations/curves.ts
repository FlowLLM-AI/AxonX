import type { BenchmarkDefinition } from "../research/backtest/types";

// An unknown return makes all later cumulative values unknown within this range.
export function performanceRows(
  rows: Record<string, unknown>[],
  benchmarks: BenchmarkDefinition[],
) {
  const values = new Map<string, number | null>();
  let peak = 1;
  const compound = (key: string, value: unknown) => {
    const previous = values.has(key) ? values.get(key)! : 1;
    const next =
      previous !== null && typeof value === "number" && Number.isFinite(value)
        ? previous * (1 + value)
        : null;
    values.set(key, next);
    return next;
  };
  return rows.map((row) => {
    const net = compound("net", row.net_return);
    if (net !== null) peak = Math.max(peak, net);
    return {
      ...row,
      ...Object.fromEntries(
        benchmarks.map(({ key }) => {
          const value = compound(
            `benchmark_${key}_return`,
            row[`benchmark_${key}_return`],
          );
          return [key, value === null ? null : value - 1];
        }),
      ),
      date: String(row.trade_date),
      net: net === null ? null : net - 1,
      drawdown: net === null ? null : net / peak - 1,
    };
  });
}
