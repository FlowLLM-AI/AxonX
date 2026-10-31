import { expect, it, vi } from "vitest";
import { table } from "../../playground/data";
import { seed } from "../../playground/fixtures";
import { loadArtifactRows } from "../../shared/api/artifacts";
import { previewWorkspaceFile } from "../../shared/api/workspace";
import { loadHistory } from "./api";
import { parseStockReport } from "./report";

vi.mock("../../shared/api/workspace", () => ({
  previewWorkspaceFile: vi.fn(),
}));
const taskId = "inference#playground_online#demo";
it("preserves the machine target and cancellation signal through pagination", async () => {
  const report = parseStockReport(
    seed().tasks.get(taskId)!.output_params.report,
  );
  vi.mocked(previewWorkspaceFile)
    .mockResolvedValueOnce({
      ...table([{ rank: 1 }]),
      kind: "parquet",
      has_more: true,
    } as Awaited<ReturnType<typeof previewWorkspaceFile>>)
    .mockResolvedValueOnce(table([{ rank: 2 }]));
  const controller = new AbortController();
  expect(
    await loadArtifactRows(
      report.commit.task_id,
      report.commit.artifacts.rankings,
      {
        target: "remote",
        signal: controller.signal,
      },
    ),
  ).toEqual([{ rank: 1 }, { rank: 2 }]);
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    {
      path: expect.stringContaining(report.commit.artifacts.rankings.path),
      offset: 5000,
      limit: 5000,
    },
    { target: "remote", signal: controller.signal },
  );
});
it("rejects partial history previews and non-Parquet data", async () => {
  const report = parseStockReport(
    seed().tasks.get(taskId)!.output_params.report,
  );
  vi.mocked(previewWorkspaceFile).mockResolvedValue({
    kind: "json",
    size: 1,
    content: "",
    data: {},
    parse_error: null,
    truncated: true,
  });
  await expect(loadHistory(taskId)).rejects.toThrow("Invalid JSON file");
  await expect(
    loadArtifactRows(report.commit.task_id, report.commit.artifacts.rankings),
  ).rejects.toThrow("Parquet");
});

function preview(data: unknown) {
  return {
    kind: "json",
    size: 100,
    data,
    content: "",
    truncated: false,
    parse_error: null,
  } as Awaited<ReturnType<typeof previewWorkspaceFile>>;
}

it("loads the selected daily model from metadata without reading mutable children", async () => {
  const source = seed().tasks.get("base#playground_online#demo")!;
  const models = source.output_params.models as Record<
    string,
    Record<string, { report: ReturnType<typeof parseStockReport> }>
  >;
  models["1445"].demo.report.commit.protocol.history_sources = [];
  const options = { target: "remote", signal: new AbortController().signal };
  vi.mocked(previewWorkspaceFile)
    .mockReset()
    .mockResolvedValue(preview(source));
  const history = await loadHistory(
    source.task_id,
    options,
    false,
    "1445:demo",
  );
  expect(history?.commits).toHaveLength(1);
  expect(history?.commits[0].task_id).toBe(source.task_id);
  expect(previewWorkspaceFile).toHaveBeenCalledTimes(1);
  expect(previewWorkspaceFile).toHaveBeenCalledWith(
    {
      path: `tasks/base/${source.task_id}/metadata.json`,
      offset: 0,
      limit: 1,
    },
    options,
  );
  await expect(
    loadHistory(source.task_id, options, true, "1445:other"),
  ).resolves.toBeNull();
});

it("allows unpublished metadata without accepting invalid JSON or hiding read errors", async () => {
  vi.mocked(previewWorkspaceFile).mockReset().mockResolvedValueOnce(null);
  const options = { target: "remote", signal: new AbortController().signal };
  expect(await loadHistory(taskId, options, true)).toBeNull();
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    {
      path: `tasks/inference/${taskId}/metadata.json`,
      offset: 0,
      limit: 1,
      allow_missing: true,
    },
    options,
  );
  vi.mocked(previewWorkspaceFile).mockResolvedValueOnce(preview(null));
  await expect(loadHistory(taskId, options, true)).rejects.toThrow(
    "Invalid Task metadata",
  );
  vi.mocked(previewWorkspaceFile).mockRejectedValueOnce(
    new Error("Permission denied"),
  );
  await expect(loadHistory(taskId, options, true)).rejects.toThrow(
    "Permission denied",
  );
});

it.each(["task", "execution"])(
  "rejects a daily report belonging to another %s",
  async (problem) => {
    const source = structuredClone(seed().tasks.get(taskId)!);
    if (problem === "task") source.task_id = "inference#another#demo";
    else source.started_at = "2026-01-05T00:00:00Z";
    vi.mocked(previewWorkspaceFile)
      .mockReset()
      .mockResolvedValueOnce(preview(source));
    await expect(loadHistory(source.task_id)).rejects.toThrow(
      "producing Task execution",
    );
  },
);

it("follows exact daily source executions and rejects a replaced historical result", async () => {
  const current = structuredClone(
    seed().tasks.get("base#playground_online#demo")!,
  );
  const previous = structuredClone(current);
  previous.task_id = "base#a_stock_online#online-20260102";
  previous.started_at = "2026-01-02T06:00:00Z";
  const currentModels = current.output_params.models as Record<
    string,
    Record<string, { report: ReturnType<typeof parseStockReport> }>
  >;
  const previousModels = previous.output_params.models as typeof currentModels;
  const old = previousModels["1445"].demo.report.commit;
  old.task_id = previous.task_id;
  old.started_at = previous.started_at;
  old.commit_id = "a".repeat(32);
  old.trade_date = "20260102";
  old.protocol.report.date_range.end = old.trade_date;
  currentModels["1445"].demo.report.commit.protocol.history_sources = [
    {
      task_id: old.task_id,
      started_at: old.started_at,
      commit_id: old.commit_id,
    },
  ];
  vi.mocked(previewWorkspaceFile)
    .mockReset()
    .mockImplementation(async ({ path }) =>
      preview(path.includes(previous.task_id) ? previous : current),
    );
  const history = await loadHistory(current.task_id, {}, false, "1445:demo");
  expect(history?.commits.map((commit) => commit.task_id)).toEqual([
    previous.task_id,
    current.task_id,
  ]);
  old.commit_id = "b".repeat(32);
  await expect(
    loadHistory(current.task_id, {}, false, "1445:demo"),
  ).rejects.toThrow("Daily history source changed");
});
