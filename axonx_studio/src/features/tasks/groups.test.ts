import { expect, it } from "vitest";
import { groupTasks } from "./groups";
import type { TaskSummary, TaskState } from "./types";
const filters = { search: "", state: "" as const, type: "" };
const task = (
  id: string,
  state: TaskState = "succeeded",
  date = "2026-10-13T01:00:00Z",
): TaskSummary => ({
  task_id: id,
  run_id: id,
  task_type: id.split("#")[0],
  reg_name: id.split("#")[1],
  state,
  pid: 1234,
  created_at: date,
  started_at: date,
  finished_at: null,
  error: "",
  exit_code: 0,
  log_path: "",
});
it("groups by type and registration, with active groups first and newest members first", () => {
  const groups = groupTasks(
    [
      task("analysis#sweep#old", "succeeded", "2026-10-12T01:00:00Z"),
      task("analysis#sweep#new"),
      task("train#sweep#active", "running", "2026-10-11T01:00:00Z"),
    ],
    filters,
  );
  expect(groups.map((group) => group.key)).toEqual([
    "train#sweep",
    "analysis#sweep",
  ]);
  expect(groups[1].tasks.map((item) => item.task_id)).toEqual([
    "analysis#sweep#new",
    "analysis#sweep#old",
  ]);
  expect(groups[1].counts).toEqual({ succeeded: 2 });
});
it("filters actual tasks while retaining the whole group count", () => {
  const tasks = [
    task("analysis#sweep#good"),
    task("analysis#sweep#bad", "failed"),
    task("train#other#bad", "cancelled"),
  ];
  const groups = groupTasks(tasks, {
    search: "BAD",
    state: "attention",
    type: "analysis",
  });
  expect(groups).toHaveLength(1);
  expect(groups[0].total).toBe(2);
  expect(groups[0].tasks.map((item) => item.task_id)).toEqual([
    "analysis#sweep#bad",
  ]);
  expect(groups[0].counts).toEqual({ failed: 1 });
  expect(groupTasks(tasks, { ...filters, search: "missing" })).toEqual([]);
});
it("handles absent and invalid timestamps deterministically", () => {
  const records = [
    task("analysis#b#one", "queued", "invalid"),
    { ...task("analysis#a#one"), started_at: null, created_at: null },
  ];
  expect(groupTasks(records, filters).map((group) => group.key)).toEqual([
    "analysis#b",
    "analysis#a",
  ]);
});
