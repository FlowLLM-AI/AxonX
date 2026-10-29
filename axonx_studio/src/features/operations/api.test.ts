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

function historyNodeFixture() {
  const report = parseStockReport(
    seed().tasks.get(taskId)!.output_params.report,
  );
  const first = structuredClone(report.commit);
  first.commit_id = "a".repeat(32);
  first.revision = 1;
  const second = structuredClone(first);
  second.commit_id = "b".repeat(32);
  second.revision = 2;
  const node = (commits: (typeof first)[], previous: unknown = null) => ({
    version: 1,
    task_type: "inference",
    kind: "online_history_node",
    strategy_identity: first.protocol.report.strategy_identity,
    commits,
    previous,
  });
  const reference = {
    path: `persistent/online/commits/${first.commit_id}/history.json`,
    size: 100,
    revision: "100:1",
  };
  const preview = (data: unknown) =>
    ({
      kind: "json",
      size: 100,
      data,
      content: "",
      truncated: false,
      parse_error: null,
    }) as Awaited<ReturnType<typeof previewWorkspaceFile>>;
  return { first, second, node, reference, preview };
}

it("loads frozen history blocks in order and validates revisions across the boundary", async () => {
  const { first, second, node, reference, preview } = historyNodeFixture();
  vi.mocked(previewWorkspaceFile)
    .mockReset()
    .mockResolvedValueOnce(preview(node([second], reference)))
    .mockResolvedValueOnce(preview(node([first])));
  const options = { target: "remote", signal: new AbortController().signal };
  const history = await loadHistory(taskId, options);
  expect(history.commits).toEqual([first, second]);
  expect(previewWorkspaceFile).toHaveBeenLastCalledWith(
    {
      path: `tasks/inference/${taskId}/${reference.path}`,
      offset: 0,
      limit: 1,
    },
    options,
  );
});

it.each(["cycle", "strategy", "revision", "path"])(
  "rejects invalid frozen history: %s",
  async (problem) => {
    const { first, second, node, reference, preview } = historyNodeFixture();
    const tail = node([second], reference);
    const previous = node([first]);
    if (problem === "cycle") previous.previous = reference;
    if (problem === "strategy") previous.strategy_identity = "f".repeat(64);
    if (problem === "revision") second.revision = 3;
    if (problem === "path") reference.path = "../other/history.json";
    vi.mocked(previewWorkspaceFile)
      .mockReset()
      .mockResolvedValueOnce(preview(tail))
      .mockResolvedValueOnce(preview(previous));
    await expect(loadHistory(taskId)).rejects.toThrow();
  },
);
