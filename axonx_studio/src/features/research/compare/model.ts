import type { DailyRow, Holding } from "../backtest/types";

export interface PairedDay {
  date: string;
  a: DailyRow;
  b: DailyRow;
}

export interface StrategyStats {
  cumulative: number;
  annualized: number;
  volatility: number;
  maxDrawdown: number;
  winRate: number;
  turnover: number;
}

export const finite = (value: unknown) =>
  value == null || value === "" ? NaN : Number(value);

export function pairDays(
  a: DailyRow[],
  b: DailyRow[],
  topN: number,
): PairedDay[] {
  const other = new Map(b.map((row) => [row.trade_date, row]));
  return a
    .flatMap((row) => {
      const match = other.get(row.trade_date);
      return match &&
        Number.isFinite(finite(row[`top${topN}_net_return`])) &&
        Number.isFinite(finite(match[`top${topN}_net_return`]))
        ? [{ date: row.trade_date, a: row, b: match }]
        : [];
    })
    .sort((left, right) => left.date.localeCompare(right.date));
}

export function cumulativeSeries(
  points: PairedDay[],
  topN: number,
  mode: "net" | "gross" = "net",
) {
  let a = mode === "net" ? 1 : 0;
  let b = mode === "net" ? 1 : 0;
  return [
    { date: "__start__", a: 0, b: 0 },
    ...points.map((point) => {
      const left = finite(point.a[`top${topN}_${mode}_return`]);
      const right = finite(point.b[`top${topN}_${mode}_return`]);
      if (Number.isFinite(left)) a = mode === "net" ? a * (1 + left) : a + left;
      if (Number.isFinite(right))
        b = mode === "net" ? b * (1 + right) : b + right;
      return {
        date: point.date,
        a: mode === "net" ? a - 1 : a,
        b: mode === "net" ? b - 1 : b,
      };
    }),
  ];
}

export function strategyStats(
  points: PairedDay[],
  side: "a" | "b",
  topN: number,
  annualizationDays = 252,
): StrategyStats {
  const returns = points.map((point) =>
    finite(point[side][`top${topN}_net_return`]),
  );
  const valid = returns.filter(Number.isFinite);
  let equity = 1;
  let peak = 1;
  let maxDrawdown = 0;
  valid.forEach((value) => {
    equity *= 1 + value;
    peak = Math.max(peak, equity);
    maxDrawdown = Math.min(maxDrawdown, equity / peak - 1);
  });
  const mean = valid.length
    ? valid.reduce((sum, value) => sum + value, 0) / valid.length
    : NaN;
  const variance =
    valid.length > 1
      ? valid.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
        (valid.length - 1)
      : NaN;
  const turnover = points
    .map((point) => finite(point[side][`top${topN}_turnover`]))
    .filter(Number.isFinite);
  return {
    cumulative: valid.length ? equity - 1 : NaN,
    annualized:
      valid.length && equity > 0
        ? equity ** (annualizationDays / valid.length) - 1
        : NaN,
    volatility: Math.sqrt(variance) * Math.sqrt(annualizationDays),
    maxDrawdown: valid.length ? maxDrawdown : NaN,
    winRate: valid.length
      ? valid.filter((value) => value > 0).length / valid.length
      : NaN,
    turnover: turnover.length
      ? turnover.reduce((sum, value) => sum + value, 0) / turnover.length
      : NaN,
  };
}

export type PeriodUnit = "year" | "quarter" | "month";
export function periodKey(date: string, unit: PeriodUnit) {
  const year = date.slice(0, 4);
  const month = Number(date.slice(4, 6));
  if (unit === "year") return year;
  if (unit === "quarter") return `${year}Q${Math.ceil(month / 3)}`;
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function periodComparison(
  points: PairedDay[],
  topN: number,
  unit: PeriodUnit,
) {
  const groups = new Map<string, PairedDay[]>();
  points.forEach((point) => {
    const key = periodKey(point.date, unit);
    groups.set(key, [...(groups.get(key) || []), point]);
  });
  return [...groups].map(([period, days]) => ({
    period,
    days: days.length,
    a: strategyStats(days, "a", topN).cumulative,
    b: strategyStats(days, "b", topN).cumulative,
  }));
}

export function pairedMean(points: PairedDay[], key: string) {
  const both = points.filter(
    (point) =>
      Number.isFinite(finite(point.a[key])) &&
      Number.isFinite(finite(point.b[key])),
  );
  const mean = (side: "a" | "b") =>
    both.length
      ? both.reduce((sum, point) => sum + finite(point[side][key]), 0) /
        both.length
      : NaN;
  return { a: mean("a"), b: mean("b"), days: both.length };
}

export function pairedRatio(
  points: PairedDay[],
  key: string,
  annualizationDays = 252,
) {
  const both = points.filter(
    (point) =>
      Number.isFinite(finite(point.a[key])) &&
      Number.isFinite(finite(point.b[key])),
  );
  const ratio = (side: "a" | "b") => {
    const values = both.map((point) => finite(point[side][key]));
    if (values.length < 2) return NaN;
    const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
    const variance =
      values.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
      (values.length - 1);
    return variance > 0
      ? (mean / Math.sqrt(variance)) * Math.sqrt(annualizationDays)
      : NaN;
  };
  return { a: ratio("a"), b: ratio("b"), days: both.length };
}

export function rollingQuality(points: PairedDay[], key: string, window = 20) {
  return points.map((point, index) => {
    const recent = points.slice(Math.max(0, index - window + 1), index + 1);
    const mean = (side: "a" | "b") => {
      const values = recent
        .map((item) => finite(item[side][key]))
        .filter(Number.isFinite);
      return values.length
        ? values.reduce((sum, value) => sum + value, 0) / values.length
        : null;
    };
    return { date: point.date, a: mean("a"), b: mean("b") };
  });
}

export function holdingOverlap(a: Holding[], b: Holding[]) {
  const aCodes = new Set(a.map((item) => item.ts_code));
  const bCodes = new Set(b.map((item) => item.ts_code));
  const common = [...aCodes].filter((code) => bCodes.has(code));
  const total = new Set([...aCodes, ...bCodes]).size;
  return {
    common,
    onlyA: a.filter((item) => !bCodes.has(item.ts_code)),
    onlyB: b.filter((item) => !aCodes.has(item.ts_code)),
    ratio: total ? common.length / total : NaN,
  };
}
