import { expect, it } from "vitest";
import { schedules, taskStatus } from "../../playground/fixtures";
import type { Schedule, TaskSummary } from "../tasks/types";
import type { ScheduleTrigger } from "../../shared/api/contracts";
import { buildOperationTree, searchOperationTree } from "./tree";

function scheduledTask(
  source: ScheduleTrigger | null,
  name = "download",
): TaskSummary {
  return {
    ...taskStatus("api", `api#download#${name}`, name),
    display_name: name,
    category: "data_update",
    source: { kind: "submit", schedule: source },
    is_online: false,
    is_replica: false,
    step_progress: null,
  };
}
const schedule = (): Schedule =>
  structuredClone(schedules.find((item) => item.name === "data_update")!);

it("groups by exact schedule provenance and keeps manual runs independent", () => {
  const first = schedule();
  const second = {
    ...first,
    name: "data_update_0926",
    scheduler_id: "second",
    history: [],
    last_trigger: null,
  };
  const source = {
    ...first.last_trigger!,
    name: second.name,
    scheduler_id: second.scheduler_id,
    trigger_id: "second-trigger",
  };
  const tree = buildOperationTree(
    [first.name, second.name],
    [first, second],
    [
      scheduledTask(first.last_trigger),
      scheduledTask(source, "same-registration"),
      scheduledTask(null, "manual"),
    ],
  );
  expect(tree.groups.map((group) => group.runs.map((run) => run.kind))).toEqual(
    [["task"], ["task"]],
  );
  expect(tree.manual.map((run) => run.id)).toEqual(["api#download#manual"]);
});

it("does not attach an old service's run to a new same-name scheduler without evidence", () => {
  const current = schedule();
  const old = {
    ...current.last_trigger!,
    scheduler_id: "old-service",
    trigger_id: "old-trigger",
  };
  const tree = buildOperationTree(
    [current.name],
    [current],
    [scheduledTask(old)],
  );
  expect(tree.groups).toHaveLength(2);
  expect(tree.groups[0].runs.every((run) => run.kind === "job")).toBe(true);
  expect(tree.groups[1].archived).toBe(true);
  expect(tree.groups[1].runs[0].id).toBe("api#download#download");
  expect(tree.manual).toHaveLength(0);
  current.history = [old];
  expect(
    buildOperationTree([current.name], [current], [scheduledTask(old)]).groups,
  ).toHaveLength(1);
});

it("deduplicates current and persisted Job triggers", () => {
  const current = schedule();
  current.job = "sync_flush";
  current.last_trigger = { ...current.last_trigger!, job: current.job };
  const failed = {
    ...current.last_trigger!,
    trigger_id: "failed-submit",
    state: "failed" as const,
    error: "Submission rejected",
  };
  current.history = [failed, current.last_trigger!];
  const tree = buildOperationTree(
    [current.name],
    [current],
    [scheduledTask(current.last_trigger)],
  );
  expect(tree.groups[0].runs.map((run) => run.kind).sort()).toEqual([
    "job",
    "task",
  ]);
  expect(tree.groups[0].runs.find((run) => run.kind === "job")?.id).toBe(
    "trigger:failed-submit",
  );
  expect(
    buildOperationTree([current.name], [current], []).groups[0].runs,
  ).toHaveLength(2);
});

it("hides successful submission history after a same-name Task is replaced", () => {
  const current = schedule();
  current.history = [
    { ...current.last_trigger!, trigger_id: "previous-submit" },
  ];
  const task = scheduledTask(current.last_trigger);
  task.state = "failed";
  const tree = buildOperationTree([current.name], [current], [task]);
  expect(tree.groups[0].runs.map((run) => run.id)).toEqual([task.task_id]);
  expect(current.history).toHaveLength(1);
});

it.each(["running", "succeeded", "failed", "cancelled"] as const)(
  "retains %s submission diagnostics until a Task exists, except successful old submissions",
  (state) => {
    const current = schedule();
    current.last_trigger = { ...current.last_trigger!, state };
    const runs = buildOperationTree([current.name], [current], []).groups[0]
      .runs;
    expect(runs.map((run) => run.id)).toEqual(
      state === "succeeded"
        ? []
        : [`trigger:${current.last_trigger.trigger_id}`],
    );
  },
);

it("keeps successful Jobs that perform work rather than submit Tasks", () => {
  const current = schedule();
  current.job = "sync_flush";
  current.last_trigger = { ...current.last_trigger!, job: current.job };
  expect(
    buildOperationTree([current.name], [current], []).groups[0].runs,
  ).toHaveLength(1);
});

it("searches run names within their groups without mutating the full tree", () => {
  const current = schedule();
  const tree = buildOperationTree(
    [current.name],
    [current],
    [scheduledTask(current.last_trigger), scheduledTask(null, "manual")],
  );
  const result = searchOperationTree(tree, "manual");
  expect(result.groups).toHaveLength(0);
  expect(result.manual).toHaveLength(1);
  expect(tree.groups).toHaveLength(1);
  expect(searchOperationTree(tree, "0 17").groups[0].runs).toHaveLength(1);
});

it("keeps empty schedules searchable by description and cron", () => {
  const current = { ...schedule(), last_trigger: null, history: [] };
  const tree = buildOperationTree([current.name], [current], []);
  expect(searchOperationTree(tree, "synthetic").groups).toHaveLength(1);
  expect(searchOperationTree(tree, "0 17").groups).toHaveLength(1);
});
