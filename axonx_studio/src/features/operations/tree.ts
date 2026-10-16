import type { ScheduleRun, ScheduleTrigger } from "../../shared/api/contracts";
import type { Schedule, TaskSummary } from "../tasks/types";

export type OperationRun =
  | { kind: "task"; id: string; task: TaskSummary }
  | { kind: "job"; id: string; run: ScheduleRun };

export interface OperationGroup {
  id: string;
  name: string;
  schedule: Schedule | null;
  archived: boolean;
  runs: OperationRun[];
}

export function triggerKey(trigger: ScheduleTrigger) {
  return JSON.stringify([
    trigger.name,
    trigger.job,
    trigger.scheduler_id,
    trigger.trigger_id,
  ]);
}

export function scheduleHistory(schedule: Schedule): ScheduleRun[] {
  const records = new Map(
    (schedule.history || []).map((run) => [triggerKey(run), run]),
  );
  if (schedule.last_trigger)
    records.set(triggerKey(schedule.last_trigger), schedule.last_trigger);
  return [...records.values()];
}

function ownsTrigger(schedule: Schedule, source: ScheduleTrigger) {
  return (
    source.name === schedule.name &&
    source.job === schedule.job &&
    (source.scheduler_id === schedule.scheduler_id ||
      scheduleHistory(schedule).some(
        (run) => triggerKey(run) === triggerKey(source),
      ))
  );
}

export function runDate(run: OperationRun) {
  return run.kind === "task"
    ? run.task.started_at || run.task.created_at || ""
    : run.run.triggered_at;
}

export function runLabel(run: OperationRun) {
  return run.kind === "task"
    ? `${run.task.display_name} ${run.task.task_id} ${run.task.source.schedule?.name || ""}`
    : `${run.run.job} ${run.run.trigger_id}`;
}

export function buildOperationTree(
  names: string[],
  schedules: Schedule[],
  tasks: TaskSummary[],
) {
  const groups: OperationGroup[] = names.map((name) => ({
    id: `schedule:${name}`,
    name,
    schedule: schedules.find((schedule) => schedule.name === name) || null,
    archived: false,
    runs: [],
  }));
  const manual: OperationRun[] = [];
  const taskTriggers = new Set<string>();
  for (const task of tasks) {
    const run: OperationRun = { kind: "task", id: task.task_id, task };
    const source = task.source.schedule;
    if (!source) {
      manual.push(run);
      continue;
    }
    taskTriggers.add(triggerKey(source));
    let group = groups.find(
      (group) => group.schedule && ownsTrigger(group.schedule, source),
    );
    if (!group) {
      const id = `archived:${JSON.stringify([source.name, source.job, source.scheduler_id])}`;
      group = groups.find((group) => group.id === id);
      if (!group) {
        group = {
          id,
          name: source.name,
          schedule: null,
          archived: true,
          runs: [],
        };
        groups.push(group);
      }
    }
    group.runs.push(run);
  }
  for (const group of groups) {
    for (const run of group.schedule ? scheduleHistory(group.schedule) : []) {
      if (!taskTriggers.has(triggerKey(run)))
        group.runs.push({ kind: "job", id: `trigger:${run.trigger_id}`, run });
    }
    group.runs.sort((a, b) => runDate(b).localeCompare(runDate(a)));
  }
  return { groups, manual };
}

export function searchOperationTree(
  tree: ReturnType<typeof buildOperationTree>,
  query: string,
) {
  const text = query.trim().toLowerCase();
  const matches = (value: string) => value.toLowerCase().includes(text);
  return {
    groups: tree.groups.flatMap((group) => {
      const groupMatches = matches(
        `${group.name} ${group.schedule?.description || ""} ${group.schedule?.cron || ""}`,
      );
      const runs = groupMatches
        ? group.runs
        : group.runs.filter((run) => matches(runLabel(run)));
      return !text || runs.length || groupMatches ? [{ ...group, runs }] : [];
    }),
    manual: tree.manual.filter((run) => matches(runLabel(run))),
  };
}
