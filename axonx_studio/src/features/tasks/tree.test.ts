import { expect, it, vi } from "vitest";
import { seed } from "../../playground/fixtures";
import { getTaskStatus } from "./api";
import { readTaskChildren } from "./tree";
import type { TaskMetadata } from "./types";

vi.mock("./api", () => ({ getTaskStatus: vi.fn() }));

it("retains the current nested Run when another branch references an older Run of the same Task", async () => {
  const parent = structuredClone(
    seed().tasks.get("composite#playground_online#demo")!,
  );
  const record = parent.children[0];
  const branch = (id: string): TaskMetadata => ({
    ...structuredClone(parent),
    task_id: id,
    run_id: id,
  });
  const first = branch("composite#test#first"),
    second = branch("composite#test#second");
  const leaf = branch("etl#test#shared");
  leaf.children = [];
  parent.children = [first, second].map((child) => ({
    ...record,
    task_id: child.task_id,
    run_id: child.run_id,
  }));
  first.children = [{ ...record, task_id: leaf.task_id, run_id: "old-run" }];
  second.children = [{ ...record, task_id: leaf.task_id, run_id: leaf.run_id }];
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
  expect(nodes.find((node) => node.record.run_id === "old-run")?.error).toBe(
    "replaced",
  );
  expect(nodes.find((node) => node.record.run_id === "old-run")?.issue).toBe(
    "replaced",
  );
  expect(
    nodes.find((node) => node.status?.task_id === leaf.task_id)?.status?.run_id,
  ).toBe(leaf.run_id);
  expect(
    vi.mocked(getTaskStatus).mock.calls.filter(([id]) => id === leaf.task_id),
  ).toHaveLength(1);
});
