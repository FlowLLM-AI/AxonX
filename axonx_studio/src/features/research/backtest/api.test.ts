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
  ...taskStatus("backtest", "backtest#demo", "demo"),
  created_at: "",
  reg_name: "demo",
  task_type: "backtest",
  output_params: {
    protocol: { version: 1, task_type: "backtest" },
    signals_format: "stock-signals-v1",
    default_universe: "all",
    universes: {
      all: {
        label: "All market",
        parameters: {},
        dimensions: { top_ns: [1], holding_detail_top_n: 30, benchmarks: [] },
        date_range: { start: "20260105", end: "20260106" },
        days: 2,
        evaluation_status: "done",
        artifacts: { daily: "daily", summary: "summary", signals: "signals" },
      },
    },
    artifacts: {
      daily: file,
      summary: { ...file, path: "summary.parquet" },
      signals: { ...file, path: "signals.parquet" },
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
    await loadBacktestDaily(meta, "all", {
      target: "remote",
      signal: controller.signal,
    }),
  ).toHaveLength(2);
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    { path: "backtest/backtest#demo/daily.parquet", offset: 5000, limit: 5000 },
    { target: "remote", signal: controller.signal },
  );
  vi.mocked(previewWorkspaceFile).mockResolvedValue(table([]));
  await expect(
    loadBacktest(meta, "all", { target: "remote", signal: controller.signal }),
  ).resolves.toEqual({ daily: [], summary: [] });
});
it.each([loadBacktest, loadBacktestDaily])(
  "still rejects legacy artifacts before requesting data",
  async (load) => {
    for (const legacy of [
      {
        ...meta,
        output_params: { ...meta.output_params, signals_format: undefined },
      },
      {
        ...meta,
        output_params: {
          ...meta.output_params,
          signals_format: undefined,
          universes: {},
        },
      },
    ]) {
      await expect(
        load(legacy as unknown as BacktestArtifact, "all"),
      ).rejects.toThrow(i18n.t("backtest.errors.signalsFormat"));
    }
    expect(previewWorkspaceFile).not.toHaveBeenCalled();
  },
);

it("rejects a missing universe instead of loading top-level artifacts", async () => {
  await expect(
    loadBacktest(
      { ...meta, output_params: { ...meta.output_params, universes: {} } },
      "all",
    ),
  ).rejects.toThrow(i18n.t("backtest.errors.missingUniverse"));
  expect(previewWorkspaceFile).not.toHaveBeenCalled();
});
