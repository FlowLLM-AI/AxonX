import { beforeEach, expect, it, vi } from "vitest";
import { loadArtifactRows } from "../../shared/api/artifacts";
import { ArtifactTableCache } from "./artifactCache";
import { seed } from "../../playground/fixtures";
import { parseStockReport, type OnlineHistory } from "./report";

vi.mock(import("../../shared/api/artifacts"), async (original) => ({
  ...(await original()),
  loadArtifactRows: vi.fn(),
}));
const artifact = { path: "signal.parquet", size: 10, revision: "1:1" };
beforeEach(() => vi.resetAllMocks());

it("assembles daily snapshots through the selected publication without duplicating cumulative ledgers", async () => {
  const current = parseStockReport(
    seed().tasks.get("inference#playground_online#demo")!.output_params.report,
  ).commit;
  const previous = structuredClone(current);
  previous.commit_id = "f".repeat(32);
  previous.task_id = "base#a_stock_online#demo-20260102";
  previous.trade_date = "20260102";
  const history: OnlineHistory = {
    version: 1,
    task_type: "inference",
    kind: "online_history",
    strategy_identity: current.protocol.report.strategy_identity,
    commits: [previous, current],
  };
  const portfolio_key = Object.keys(current.protocol.report.portfolios)[0];
  vi.mocked(loadArtifactRows).mockImplementation(async (id) => [
    {
      trade_date:
        id === previous.task_id ? previous.trade_date : current.trade_date,
      portfolio_key,
      net_value: id === previous.task_id ? 1.01 : 1.02,
    },
  ]);
  const cache = new ArtifactTableCache(current.task_id);
  expect(await cache.ledger(current, history, "daily")).toEqual([
    { trade_date: previous.trade_date, portfolio_key, net_value: 1.01 },
    { trade_date: current.trade_date, portfolio_key, net_value: 1.02 },
  ]);
  expect(await cache.ledger(previous, history, "daily")).toHaveLength(1);
  expect(loadArtifactRows).toHaveBeenCalledTimes(2);
  expect(await cache.ledger(current, history, "positions")).toHaveLength(1);
  vi.mocked(loadArtifactRows).mockResolvedValue([
    { trade_date: previous.trade_date, portfolio_key },
  ]);
  await expect(cache.ledger(current, history, "orders")).rejects.toThrow(
    "daily publication",
  );
});

it("shares in-flight and completed tables, isolating content and service identity", async () => {
  const rows = [{ ts_code: "000001" }];
  let finish!: (value: typeof rows) => void;
  vi.mocked(loadArtifactRows).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const cache = new ArtifactTableCache("inference#test#one", "remote");
  const first = cache.load(artifact);
  const second = cache.load(artifact);
  expect(loadArtifactRows).toHaveBeenCalledOnce();
  finish(rows);
  expect(await first).toBe(rows);
  expect(await second).toBe(rows);
  expect(await cache.load(artifact)).toBe(rows);
  vi.mocked(loadArtifactRows).mockResolvedValue(rows);
  await cache.load({ ...artifact, revision: "1:2" });
  await new ArtifactTableCache("inference#test#one", "other").load(artifact);
  expect(loadArtifactRows).toHaveBeenCalledTimes(3);
  await cache.load(artifact, undefined, "base#archive#earlier");
  expect(loadArtifactRows).toHaveBeenLastCalledWith(
    "base#archive#earlier",
    artifact,
    {
      target: "remote",
      signal: expect.any(AbortSignal),
    },
  );
});

it("bounds retained data and retries failures", async () => {
  const cache = new ArtifactTableCache("inference#test#one", undefined, 1);
  vi.mocked(loadArtifactRows)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue([{ value: 1 }]);
  await expect(cache.load(artifact)).rejects.toThrow("offline");
  await cache.load(artifact);
  await cache.load(artifact);
  expect(loadArtifactRows).toHaveBeenCalledTimes(3);
});

it("cancelling one tab preserves shared work, while disposal cancels owned requests", async () => {
  let finish!: (value: Record<string, unknown>[]) => void;
  vi.mocked(loadArtifactRows).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const cache = new ArtifactTableCache("inference#test#one");
  const controller = new AbortController();
  const first = cache.load(artifact, controller.signal);
  const rejected = expect(first).rejects.toMatchObject({ name: "AbortError" });
  controller.abort();
  const second = cache.load(artifact);
  finish([]);
  await rejected;
  await expect(second).resolves.toEqual([]);
  expect(loadArtifactRows).toHaveBeenCalledOnce();
  vi.mocked(loadArtifactRows).mockImplementationOnce(
    async (_task, _artifact, { signal } = {}) => {
      return new Promise((_resolve, reject) =>
        signal!.addEventListener("abort", () => reject(signal!.reason), {
          once: true,
        }),
      );
    },
  );
  const pending = cache.load({ ...artifact, path: "other.parquet" });
  const disposed = expect(pending).rejects.toMatchObject({
    name: "AbortError",
  });
  cache.clear();
  await disposed;
});
