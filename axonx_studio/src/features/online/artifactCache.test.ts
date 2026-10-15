import { beforeEach, expect, it, vi } from "vitest";
import { loadArtifactRows } from "./api";
import { ArtifactTableCache } from "./artifactCache";

vi.mock("./api", () => ({ loadArtifactRows: vi.fn() }));
const artifact = { path: "signal.parquet", size: 10, sha256: "a".repeat(64) };
beforeEach(() => vi.resetAllMocks());

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
  await cache.load({ ...artifact, sha256: "b".repeat(64) });
  await new ArtifactTableCache("inference#test#one", "other").load(artifact);
  expect(loadArtifactRows).toHaveBeenCalledTimes(3);
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
    async (_task, _artifact, _target, signal) => {
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
