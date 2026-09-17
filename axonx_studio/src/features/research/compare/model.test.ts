import { describe, expect, it } from "vitest";
import type { DailyRow } from "../backtest/types";
import {
  cumulativeSeries,
  holdingOverlap,
  pairDays,
  periodComparison,
  strategyStats,
} from "./model";

const day = (date: string, net: number, gross = net): DailyRow => ({
  trade_date: date,
  candidate_count: 30,
  ic: 0,
  rank_ic: 0,
  top30_holdings: [],
  top30_net_return: net,
  top30_gross_return: gross,
  top30_turnover: 0.2,
});

describe("strategy comparison", () => {
  it("aligns dates before compounding either strategy", () => {
    const a = [
      day("20230102", 0.5),
      day("20230103", 0.1),
      day("20230104", -0.1),
    ];
    const b = [
      day("20230103", 0.2),
      day("20230104", 0.1),
      day("20230105", 0.7),
    ];
    const paired = pairDays(a, b, 30);
    expect(paired.map((point) => point.date)).toEqual(["20230103", "20230104"]);
    expect(cumulativeSeries(paired, 30).at(-1)?.a).toBeCloseTo(-0.01);
    expect(cumulativeSeries(paired, 30).at(-1)?.b).toBeCloseTo(0.32);
    expect(strategyStats(paired, "a", 30).maxDrawdown).toBeCloseTo(-0.1);
  });

  it("restarts compounding within each displayed period", () => {
    const paired = pairDays(
      [day("20231229", 0.1), day("20240102", 0.2)],
      [day("20231229", 0.05), day("20240102", 0.1)],
      30,
    );
    const result = periodComparison(paired, 30, "year");
    expect(result.map((row) => row.period)).toEqual(["2023", "2024"]);
    expect(result[0].a).toBeCloseTo(0.1);
    expect(result[0].b).toBeCloseTo(0.05);
    expect(result[1].a).toBeCloseTo(0.2);
    expect(result[1].b).toBeCloseTo(0.1);
  });

  it("computes stock overlap from unique codes", () => {
    const holding = (ts_code: string) => ({
      rank: 1,
      ts_code,
      name: ts_code,
      prediction: 0,
      daily_return: 0,
      weight: 0.5,
    });
    const overlap = holdingOverlap(
      [holding("A"), holding("B")],
      [holding("B"), holding("C")],
    );
    expect(overlap.common).toEqual(["B"]);
    expect(overlap.ratio).toBeCloseTo(1 / 3);
  });
});
