import { expect, it, vi } from "vitest";
import { previewWorkspaceFile } from "../workspace/api";
import { loadHistory, loadRows } from "./api";
import { seed, table } from "../../playground/fixtures";
import { parseStockReport } from "./report";

vi.mock("../workspace/api", () => ({ previewWorkspaceFile: vi.fn() }));
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
    await loadRows(report.commit, "signal", "remote", controller.signal),
  ).toEqual([{ rank: 1 }, { rank: 2 }]);
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    expect.stringContaining(report.commit.artifacts.signal.path),
    5000,
    5000,
    "remote",
    controller.signal,
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
  await expect(loadHistory(taskId)).rejects.toThrow(
    "Invalid online history file",
  );
  await expect(loadRows(report.commit, "signal")).rejects.toThrow(
    "Expected Parquet",
  );
});
