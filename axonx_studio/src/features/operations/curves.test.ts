import { expect, it } from "vitest";
import { performanceRows } from "./curves";

const rows = [0.1, -0.05, 0.2].map((value, i) => ({
  trade_date: `2026101${i}`,
  net_return: value,
  benchmark_index_return: value,
}));
it("compounds returns and rebases the selected range", () => {
  const values = performanceRows(rows, [{ key: "index", label: "Index" }]);
  expect(values[1].net).toBeCloseTo(0.045);
  expect(values[1].drawdown).toBeCloseTo(-0.05);
  expect(performanceRows(rows.slice(1), [])[0].net).toBeCloseTo(-0.05);
});
it("keeps missing valuations unknown without fabricating flat returns", () => {
  const values = performanceRows(
    [
      rows[0],
      { ...rows[1], net_return: null, benchmark_index_return: NaN },
      rows[2],
    ],
    [{ key: "index", label: "Index" }],
  );
  expect(values[1]).toMatchObject({ net: null, drawdown: null, index: null });
  expect(values[2]).toMatchObject({ net: null, drawdown: null, index: null });
});
