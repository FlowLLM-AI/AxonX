import { expect, it } from "vitest";
import { cumulativeRows } from "./model";
import type { DailyRow } from "./types";

it("keeps zero equity after a complete loss and retains the gross return basis", () => {
  const rows: DailyRow[] = [
    { trade_date: "20260105", top5_net_return: -1, top5_gross_return: 0.1 },
    { trade_date: "20260106", top5_net_return: 0.5, top5_gross_return: 0.2 },
  ].map((row) => ({
    ...row,
    candidate_count: 0,
    ic: null,
    rank_ic: null,
    top30_holdings: null,
  }));
  expect(
    cumulativeRows(rows, [5], [], true, "start").map((row) => row.top5),
  ).toEqual([0, -1, -1]);
  const gross = cumulativeRows(rows, [5], [], false, "start");
  expect(gross[2].top5).toBeCloseTo(0.3);
});
