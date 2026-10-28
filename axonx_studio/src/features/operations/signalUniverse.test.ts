import { expect, it } from "vitest";
import {
  filterSignalUniverse,
  missingUniverseContext,
  parseUniverse,
  signalUniverses,
} from "./signalUniverse";

const rows = [
  {
    ts_code: "A",
    trade_date: "20261019",
    trade_time: "0945",
    pred: 0.9,
    is_model_candidate: true,
    is_buyable_at_signal: false,
    amount_to_signal: 1000,
    index_weight_hs300: 1,
  },
  {
    ts_code: "B",
    trade_date: "20261019",
    trade_time: "0945",
    pred: 0.8,
    is_model_candidate: true,
    is_buyable_at_signal: true,
    amount_to_signal: 100,
    index_weight_hs300: 1,
  },
  {
    ts_code: "C",
    trade_date: "20261019",
    trade_time: "0945",
    pred: 0.7,
    is_model_candidate: true,
    is_buyable_at_signal: true,
    amount_to_signal: 100,
    index_weight_hs300: 0,
  },
  {
    ts_code: "D",
    trade_date: "20261019",
    trade_time: "0945",
    pred: 0.6,
    is_model_candidate: false,
    is_buyable_at_signal: true,
    amount_to_signal: 900,
    index_weight_hs300: 1,
  },
];
const codes = (items: Record<string, unknown>[]) => items.map((r) => r.ts_code);
it("matches eligible-first percentile selection, ceil and code ties, independent of viewing blocked stocks", () => {
  const pool = parseUniverse({
    kind: "percentile",
    field: "amount_to_signal",
    top_percent: 10,
  })!;
  expect(codes(filterSignalUniverse(rows, pool, true))).toEqual(["B"]);
  expect(codes(filterSignalUniverse(rows, pool, false))).toEqual(["B"]);
  expect(
    codes(filterSignalUniverse(rows, { ...pool, top_percent: 51 }, true)),
  ).toEqual(["B", "C"]);
});
it("supports index unions and inspecting blocked stocks without admitting non-model candidates", () => {
  const pool = parseUniverse({ kind: "index", index_codes: ["hs300"] })!;
  expect(codes(filterSignalUniverse(rows, pool, true))).toEqual(["B"]);
  expect(codes(filterSignalUniverse(rows, pool, false))).toEqual(["A", "B"]);
  expect(missingUniverseContext(rows, pool)).toBe(false);
  expect(
    missingUniverseContext(
      rows,
      parseUniverse({ kind: "index", index_codes: ["zz500"] })!,
    ),
  ).toBe(true);
});
it("uses each time independently and excludes missing, zero and non-finite percentile values", () => {
  const pool = parseUniverse({
    kind: "percentile",
    field: "amount_to_signal",
    top_percent: 50,
  })!;
  const extra = [null, 0, Infinity, -10].map((amount_to_signal, i) => ({
    ...rows[1],
    ts_code: `X${i}`,
    amount_to_signal,
  }));
  expect(
    codes(
      filterSignalUniverse(
        [
          ...rows,
          ...extra,
          {
            ...rows[1],
            ts_code: "E",
            trade_time: "1000",
            amount_to_signal: 10,
          },
        ],
        pool,
        true,
      ),
    ),
  ).toEqual(["B", "E"]);
});
it("recognizes the same default pool families and rejects unsupported recorded rules", () => {
  expect(signalUniverses).toHaveLength(22);
  expect(
    parseUniverse({
      kind: "percentile",
      field: "future_return",
      top_percent: 50,
    }),
  ).toBeNull();
  expect(
    parseUniverse({
      kind: "percentile",
      field: "amount_to_signal",
      top_percent: 0,
    }),
  ).toBeNull();
});
