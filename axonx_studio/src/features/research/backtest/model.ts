import {
  formatFixed as fixed,
  toNumber as number,
  formatPercent as percent,
} from "../../../shared/lib/format";
import type {
  BenchmarkDefinition,
  ChartRow,
  ChartSeries,
  DailyRow,
  SummaryRow,
} from "./types";

export const IC_SERIES: ChartSeries[] = [
  { key: "ic", label: "IC" },
  { key: "rank_ic", label: "RankIC" },
];

export const lastOnOrBefore = (rows: DailyRow[], date: string) => {
  let index = 0;
  rows.forEach((row, current) => {
    if (row.trade_date <= date) index = current;
  });
  return index;
};

function movingAverage(rows: DailyRow[], key: string, window = 20) {
  return rows.map((_, index) => {
    const values = rows
      .slice(Math.max(0, index - window + 1), index + 1)
      .map((row) => number(row[key]))
      .filter(Number.isFinite);
    return values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : null;
  });
}

export function cumulativeRows(
  rows: DailyRow[],
  topNs: number[],
  benchmarks: BenchmarkDefinition[],
  compound: boolean,
  startLabel: string,
): ChartRow[] {
  const totals = new Map<string, number>();
  const definitions = [
    ...topNs.map(
      (topN) =>
        [
          `top${topN}`,
          `top${topN}_${compound ? "net" : "gross"}_return`,
        ] as const,
    ),
    ...benchmarks.map(
      ({ key }) => [`benchmark_${key}`, `benchmark_${key}_return`] as const,
    ),
  ];
  for (const [key] of definitions) totals.set(key, compound ? 1 : 0);
  const result: ChartRow[] = [
    {
      date: startLabel,
      ...Object.fromEntries(definitions.map(([key]) => [key, 0])),
    },
  ];
  for (const row of rows) {
    const point: ChartRow = { date: row.trade_date };
    for (const [key, source] of definitions) {
      const daily = number(row[source]);
      if (!Number.isFinite(daily)) {
        point[key] = null;
        continue;
      }
      const next = compound
        ? totals.get(key)! * (1 + daily)
        : totals.get(key)! + daily;
      totals.set(key, next);
      point[key] = compound ? next - 1 : next;
    }
    result.push(point);
  }
  return result;
}

export function signalRows(rows: DailyRow[], topNs: number[]) {
  const ic = movingAverage(rows, "ic");
  const rankIc = movingAverage(rows, "rank_ic");
  const ndcg = topNs.map(
    (topN) => [topN, movingAverage(rows, `top${topN}_ndcg`)] as const,
  );
  return rows.map((row, index) => ({
    date: row.trade_date,
    ic: ic[index],
    rank_ic: rankIc[index],
    ...Object.fromEntries(
      ndcg.map(([topN, values]) => [`ndcg_${topN}`, values[index]]),
    ),
  }));
}

export type SummaryMetric = {
  key: string;
  label?: string;
  format: (value: unknown) => string;
  percent: boolean;
};

export const performanceMetrics: SummaryMetric[] = [
  {
    key: "net_cumulative_return",
    format: percent,
    percent: true,
  },
  {
    key: "net_annualized_return",
    format: percent,
    percent: true,
  },
  {
    key: "net_annualized_volatility",
    format: percent,
    percent: true,
  },
  {
    key: "net_max_drawdown",
    format: percent,
    percent: true,
  },
  {
    key: "net_win_rate",
    format: percent,
    percent: true,
  },
  {
    key: "average_turnover",
    format: percent,
    percent: true,
  },
  {
    key: "gross_cumulative_return",
    format: percent,
    percent: true,
  },
  {
    key: "gross_sharpe",
    format: fixed,
    percent: false,
  },
];

export const signalMetrics: SummaryMetric[] = [
  {
    key: "trading_days",
    format: (value) => fixed(value, 0),
    percent: false,
  },
  {
    key: "ic_mean",
    format: (value) => fixed(value, 4),
    percent: false,
  },
  {
    key: "icir",
    format: fixed,
    percent: false,
  },
  {
    key: "rank_ic_mean",
    format: (value) => fixed(value, 4),
    percent: false,
  },
  {
    key: "rank_icir",
    format: fixed,
    percent: false,
  },
];

export const metricValue = (row: SummaryRow, topN: number, key: string) =>
  row[`top${topN}_${key}`];

export const valueTone = (value: unknown) =>
  value == null || !Number.isFinite(Number(value))
    ? ""
    : Number(value) < 0
      ? "negative"
      : Number(value) > 0
        ? "positive"
        : "";

export type SummarySort = { key: string; direction: "asc" | "desc" } | null;

export const nextSummarySort = (
  current: SummarySort,
  key: string,
): SummarySort => ({
  key,
  direction:
    current?.key === key && current.direction === "asc" ? "desc" : "asc",
});

export const dataBarDomain = (values: unknown[]) => {
  const finite = values.map(number).filter(Number.isFinite);
  return {
    min: Math.min(0, ...finite),
    max: Math.max(0, ...finite),
  };
};
