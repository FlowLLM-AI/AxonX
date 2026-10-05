import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadOnlineReport } from "./api";
import { listWorkspaceEntries, previewWorkspaceFile } from "../workspace/api";
import { taskStatus } from "../../playground/fixtures";

vi.mock("../workspace/api", () => ({
  listWorkspaceEntries: vi.fn(),
  previewWorkspaceFile: vi.fn(),
}));
beforeEach(() => vi.clearAllMocks());
describe("online incremental report", () => {
  it("reads a failed task's audit report with its machine target and abort signal", async () => {
    const task = taskStatus("inference", "inference#demo#test", "demo");
    task.state = "failed";
    task.result = {};
    const signal = new AbortController().signal;
    vi.mocked(listWorkspaceEntries).mockResolvedValueOnce({
      path: "inference",
      truncated: false,
      entries: [
        {
          name: task.task_id,
          path: `inference/${task.task_id}`,
          kind: "directory",
          preview_kind: null,
          supported: true,
          size: null,
          modified_at: 0,
        },
      ],
    });
    const path = `inference/${task.task_id}/manifest.json`;
    vi.mocked(listWorkspaceEntries).mockResolvedValueOnce({
      path: `inference/${task.task_id}`,
      truncated: false,
      entries: [
        {
          name: "manifest.json",
          path,
          kind: "file",
          preview_kind: "json",
          supported: true,
          size: 20,
          modified_at: 0,
        },
      ],
    });
    const report = {
      windows: [{ key: "1445", status: "failed", reason: "History stale" }],
    };
    vi.mocked(previewWorkspaceFile).mockResolvedValue({
      kind: "json",
      data: report,
      content: "",
      size: 20,
      parse_error: null,
      truncated: false,
    });
    expect(await loadOnlineReport(task, "remote", signal)).toEqual(report);
    expect(listWorkspaceEntries).toHaveBeenNthCalledWith(
      1,
      "inference",
      "remote",
      signal,
      0,
    );
    expect(listWorkspaceEntries).toHaveBeenNthCalledWith(
      2,
      `inference/${task.task_id}`,
      "remote",
      signal,
      0,
    );
    expect(previewWorkspaceFile).toHaveBeenCalledWith(
      path,
      0,
      200,
      "remote",
      signal,
    );
  });
  it("finds active runs beyond the first directory page", async () => {
    const task = taskStatus("inference", "inference#demo#test", "demo");
    task.state = "running";
    task.result = {};
    const entry = (name: string, path: string) => ({
      name,
      path,
      kind: "directory" as const,
      preview_kind: null,
      supported: false,
      size: null,
      modified_at: 0,
    });
    vi.mocked(listWorkspaceEntries)
      .mockResolvedValueOnce({
        path: "inference",
        truncated: true,
        entries: [entry("other", "inference/other")],
      })
      .mockResolvedValueOnce({
        path: "inference",
        truncated: false,
        entries: [entry(task.task_id, `inference/${task.task_id}`)],
      })
      .mockResolvedValueOnce({
        path: `inference/${task.task_id}`,
        truncated: false,
        entries: [],
      });
    const signal = new AbortController().signal;
    expect(await loadOnlineReport(task, "remote", signal)).toEqual({});
    expect(listWorkspaceEntries).toHaveBeenNthCalledWith(
      2,
      "inference",
      "remote",
      signal,
      1,
    );
  });

  it("treats unpublished reports as pending", async () => {
    vi.mocked(listWorkspaceEntries).mockResolvedValueOnce({
      path: "inference",
      entries: [],
      truncated: false,
    });
    expect(
      await loadOnlineReport(
        taskStatus("inference", "inference#demo#test", "demo"),
        undefined,
        new AbortController().signal,
      ),
    ).toEqual({});
    expect(previewWorkspaceFile).not.toHaveBeenCalled();
  });
});
