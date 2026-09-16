import type { ResearchArtifact } from "../types";

export type NumericRow = Record<string, unknown>;

export interface Holding {
  rank: number;
  ts_code: string;
  name: string;
  prediction: number;
  daily_return: number;
  weight: number;
}

export interface DailyRow extends NumericRow {
  trade_date: string;
  candidate_count: number;
  ic: number;
  rank_ic: number;
  top30_holdings: Holding[];
}

export interface SummaryRow extends NumericRow {
  period_type: "overall" | "year" | "quarter" | "month";
  period: string;
  period_start: string;
  period_end: string;
  trading_days: number;
  ic_mean: number;
  icir: number;
  rank_ic_mean: number;
  rank_icir: number;
}

export interface BenchmarkDefinition {
  key: string;
  label: string;
}

export interface BacktestArtifact extends ResearchArtifact {
  dimensions?: {
    top_ns?: number[];
    holding_detail_top_n?: number;
    benchmarks?: BenchmarkDefinition[];
  };
}

export interface ChartRow extends NumericRow {
  date: string;
}

export interface ChartSeries {
  key: string;
  label: string;
  dashed?: boolean;
  type?: "line" | "bar";
  axis?: 0 | 1;
}
