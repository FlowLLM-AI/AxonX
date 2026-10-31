import { beforeEach, expect, it, vi } from "vitest";
import i18n from "../../../i18n";
import { table, taskStatus } from "../../../playground/data";
import { previewWorkspaceFile } from "../../../shared/api/workspace";
import { loadBacktest, loadBacktestDaily } from "./api";
import type { BacktestArtifact } from "./types";

vi.mock("../../../shared/api/workspace", () => ({
  previewWorkspaceFile: vi.fn(),
}));
const file = { path: "daily.parquet", size: 1, revision: "1:1" };
const meta: BacktestArtifact = {
  ...taskStatus("backtest", "backtest#demo#test"),
  created_at: "",
  reg_name: "demo",
  task_type: "backtest",
  output_params: {
    protocol: { version: 1, task_type: "backtest" },
    signals_format: "stock-signals-v3",
    portfolios: [
      {
        portfolio_id: { universe: { kind: "all" }, top_n: 1 },
        dimensions: { top_ns: [1], holding_detail_top_n: 30, benchmarks: [] },
        date_range: { start: "20260105", end: "20260106" },
        days: 2,
        evaluation_status: "done",
        artifacts: { daily: "daily", summary: "summary" },
      },
    ],
    artifacts: {
      daily: file,
      summary: { ...file, path: "summary.parquet" },
    },
  },
};
beforeEach(() => vi.clearAllMocks());
it("loads current signals metadata through both report readers with pagination and target", async () => {
  const controller = new AbortController();
  vi.mocked(previewWorkspaceFile)
    .mockResolvedValueOnce({
      ...table([{ trade_date: "20260105" }]),
      kind: "parquet",
      has_more: true,
    } as Awaited<ReturnType<typeof previewWorkspaceFile>>)
    .mockResolvedValueOnce(table([{ trade_date: "20260106" }]));
  expect(
    await loadBacktestDaily(meta, "0", {
      target: "remote",
      signal: controller.signal,
    }),
  ).toHaveLength(2);
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    {
      path: "tasks/backtest/backtest#demo#test/daily.parquet",
      offset: 5000,
      limit: 5000,
    },
    { target: "remote", signal: controller.signal },
  );
  vi.mocked(previewWorkspaceFile).mockResolvedValue(table([]));
  await expect(
    loadBacktest(meta, "0", { target: "remote", signal: controller.signal }),
  ).resolves.toEqual({ daily: [], summary: [] });
});
it.each([loadBacktest, loadBacktestDaily])(
  "requires the stock signals protocol before requesting data",
  async (load) => {
    for (const invalid of [
      {
        ...meta,
        output_params: { ...meta.output_params, signals_format: undefined },
      },
      {
        ...meta,
        output_params: {
          ...meta.output_params,
          signals_format: "unknown",
        },
      },
    ]) {
      await expect(
        load(invalid as unknown as BacktestArtifact, "0"),
      ).rejects.toThrow(i18n.t("backtest.errors.signalsFormat"));
    }
    expect(previewWorkspaceFile).not.toHaveBeenCalled();
  },
);

it("rejects a missing universe instead of loading top-level artifacts", async () => {
  await expect(
    loadBacktest(
      { ...meta, output_params: { ...meta.output_params, portfolios: [] } },
      "0",
    ),
  ).rejects.toThrow(i18n.t("backtest.errors.missingPortfolio"));
  expect(previewWorkspaceFile).not.toHaveBeenCalled();
});
