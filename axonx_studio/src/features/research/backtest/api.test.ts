import { beforeEach, expect, it, vi } from "vitest";
import i18n from "../../../i18n";
import { table } from "../../../playground/fixtures";
import { previewWorkspaceFile } from "../../workspace/api";
import { loadBacktest, loadBacktestDaily } from "./api";
import type { BacktestArtifact } from "./types";

vi.mock("../../workspace/api", () => ({ previewWorkspaceFile: vi.fn() }));
const file = { path: "daily.parquet", size: 1, sha256: "digest" };
const meta: BacktestArtifact = {
  _path: "backtest/demo",
  task_key: "demo",
  created_at: "",
  config: {
    task_id: "backtest#demo",
    task_name: "demo",
    task_type: "backtest",
  },
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
    await loadBacktestDaily(meta, "all", "remote", controller.signal),
  ).toHaveLength(2);
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    "backtest/demo/daily.parquet",
    5000,
    5000,
    "remote",
    controller.signal,
  );
  vi.mocked(previewWorkspaceFile).mockResolvedValue(table([]));
  await expect(
    loadBacktest(meta, "all", "remote", controller.signal),
  ).resolves.toEqual({ daily: [], summary: [] });
});
it.each([loadBacktest, loadBacktestDaily])(
  "still rejects legacy artifacts before requesting data",
  async (load) => {
    for (const legacy of [
      { ...meta, signals_format: undefined },
      { ...meta, signals_format: undefined, universes: {} },
    ]) {
      await expect(load(legacy, "all")).rejects.toThrow(
        i18n.t("backtest.errors.signalsFormat"),
      );
    }
    expect(previewWorkspaceFile).not.toHaveBeenCalled();
  },
);

it("rejects a missing universe instead of loading top-level artifacts", async () => {
  await expect(loadBacktest({ ...meta, universes: {} }, "all")).rejects.toThrow(
    i18n.t("backtest.errors.missingUniverse"),
  );
  expect(previewWorkspaceFile).not.toHaveBeenCalled();
});
