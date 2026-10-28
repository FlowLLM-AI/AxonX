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
      report.commit.artifacts.signal,
      {
        target: "remote",
        signal: controller.signal,
      },
    ),
  ).toEqual([{ rank: 1 }, { rank: 2 }]);
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    {
      path: expect.stringContaining(report.commit.artifacts.signal.path),
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
    loadArtifactRows(report.commit.task_id, report.commit.artifacts.signal),
  ).rejects.toThrow("Parquet");
});
