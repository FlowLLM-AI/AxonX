import { expect, it, vi } from "vitest";
import { seed } from "../../playground/fixtures";
import type { TaskMetadata } from "../../shared/api/contracts";
import { getTaskStatus } from "./api";
import { readTaskChildren } from "./tree";

vi.mock("./api", () => ({ getTaskStatus: vi.fn() }));

it("retains the current nested Task when another branch references an earlier execution of the same Task", async () => {
  const parent = structuredClone(
    seed().tasks.get("base#playground_online#demo")!,
  );
  const record = parent.children[0];
  const branch = (id: string): TaskMetadata => ({
    ...structuredClone(parent),
    task_id: id,
    started_at: "2026-10-26T10:00:00Z",
  });
  const first = branch("base#test#first"),
    second = branch("base#test#second");
  const leaf = branch("etl#test#shared");
  leaf.children = [];
  parent.children = [first, second].map((child) => ({
    ...record,
    child_task_id: child.task_id,
    started_at: child.started_at,
  }));
  first.children = [
    {
      ...record,
      child_task_id: leaf.task_id,
      started_at: "2026-10-25T10:00:00Z",
    },
  ];
  second.children = [
    { ...record, child_task_id: leaf.task_id, started_at: leaf.started_at },
  ];
  const tasks = new Map(
    [first, second, leaf].map((task) => [task.task_id, task]),
  );
  vi.mocked(getTaskStatus)
    .mockClear()
    .mockImplementation(async (id) => tasks.get(id)!);
  const nodes = await readTaskChildren(
    parent,
    "selected",
    new AbortController().signal,
    { replaced: "replaced", snapshot: "snapshot" },
  );
  expect(
    nodes.find((node) => node.record.started_at === "2026-10-25T10:00:00Z")
      ?.error,
  ).toBe("replaced");
  expect(
    nodes.find((node) => node.record.started_at === "2026-10-25T10:00:00Z")
      ?.issue,
  ).toBe("replaced");
  expect(
    nodes.find((node) => node.status?.task_id === leaf.task_id)?.status
      ?.started_at,
  ).toBe(leaf.started_at);
  expect(
    vi.mocked(getTaskStatus).mock.calls.filter(([id]) => id === leaf.task_id),
  ).toHaveLength(1);
});

it("does not load an older Task while a child has not started", async () => {
  const parent = structuredClone(
    seed().tasks.get("base#playground_online#demo")!,
  );
  parent.children = [{ ...parent.children[0], started_at: null }];
  vi.mocked(getTaskStatus).mockClear();
  const nodes = await readTaskChildren(
    parent,
    undefined,
    new AbortController().signal,
    {
      replaced: "replaced",
      snapshot: "snapshot",
    },
  );
  expect(getTaskStatus).not.toHaveBeenCalled();
  expect(nodes).toEqual([
    { record: parent.children[0], status: null, error: "" },
  ]);
});
