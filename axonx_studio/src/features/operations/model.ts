import type { ScheduleRun, ScheduleTrigger } from "../../shared/api/contracts";
import type { Schedule, TaskSummary } from "../tasks/types";

export type OperationEntry = (
  | { kind: "task"; id: string; task: TaskSummary }
  | { kind: "job"; id: string; run: ScheduleRun }
  | { kind: "schedule"; id: string; name: string }
) & { schedules: Schedule[] };

export type ScheduleTask = Pick<
  TaskSummary,
  "task_id" | "task_type" | "reg_name" | "source" | "created_at"
>;

function triggerKey(trigger: ScheduleTrigger) {
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

function matchesTask(schedule: Schedule, task: ScheduleTask) {
  const source = task.source.schedule;
  const args = schedule.arguments;
  // A fixed identity associates current configuration, not the origin of this Run.
  return (
    (schedule.job === "submit" &&
      args.task === task.reg_name &&
      typeof args.task_name === "string" &&
      !!args.task_name &&
      task.task_id ===
        `${task.task_type}#${task.reg_name}#${args.task_name}`) ||
    (source !== null &&
      source.name === schedule.name &&
      source.job === schedule.job &&
      (source.scheduler_id === schedule.scheduler_id ||
        (source.scheduler_id !== null &&
          schedule.history_scheduler_ids?.includes(source.scheduler_id)) ||
        scheduleHistory(schedule).some(
          (run) => triggerKey(run) === triggerKey(source),
        )))
  );
}

export function isEarlierSubmission(schedule: Schedule, task?: ScheduleTask) {
  const last = schedule.last_trigger;
  if (
    schedule.job !== "submit" ||
    !last ||
    last.state === "queued" ||
    last.state === "running" ||
    !task?.created_at ||
    !matchesTask(schedule, task) ||
    (task.source.schedule &&
      triggerKey(task.source.schedule) === triggerKey(last))
  )
    return false;
  // A later start alone may belong to an older queued Task; compare creation.
  return (
    Date.parse(task.created_at) >
    Date.parse(last.finished_at || last.triggered_at)
  );
}

export function entryDate(entry: OperationEntry) {
  return entry.kind === "task"
    ? entry.task.started_at || entry.task.created_at || ""
    : entry.kind === "job"
      ? entry.run.triggered_at
      : "";
}

export function entryLabel(entry: OperationEntry) {
  return entry.kind === "task"
    ? entry.task.display_name || entry.task.reg_name
    : entry.kind === "job"
      ? entry.run.name
      : entry.name;
}

export function buildOperationIndex(
  names: string[],
  schedules: Schedule[],
  tasks: TaskSummary[],
): OperationEntry[] {
  const entries: OperationEntry[] = tasks.map((task) => ({
    kind: "task",
    id: task.task_id,
    task,
    schedules: schedules.filter((schedule) => matchesTask(schedule, task)),
  }));
  const taskTriggers = new Set(
    tasks.flatMap((task) =>
      task.source.schedule ? [triggerKey(task.source.schedule)] : [],
    ),
  );
  for (const schedule of schedules) {
    for (const run of scheduleHistory(schedule)) {
      if (run.job !== "submit" && !taskTriggers.has(triggerKey(run)))
        entries.push({
          kind: "job",
          id: `trigger:${run.trigger_id}`,
          run,
          schedules: [schedule],
        });
    }
  }
  for (const name of names) {
    if (!entries.some((entry) => entry.schedules.some((s) => s.name === name)))
      entries.push({
        kind: "schedule",
        id: `schedule:${name}`,
        name,
        schedules: schedules.filter((schedule) => schedule.name === name),
      });
  }
  return entries.sort((a, b) => entryDate(b).localeCompare(entryDate(a)));
}

export function searchOperationIndex(entries: OperationEntry[], query: string) {
  const text = query.trim().toLowerCase();
  return entries.filter((entry) =>
    [
      entryLabel(entry),
      entry.id,
      entry.kind === "task" ? entry.task.source.schedule?.name : "",
      entry.kind === "job" ? entry.run.job : "",
      ...entry.schedules.map((s) => `${s.name} ${s.description} ${s.cron}`),
    ]
      .join(" ")
      .toLowerCase()
      .includes(text),
  );
}

export function findOperationEntry(
  entries: OperationEntry[],
  schedules: Schedule[],
  id: string,
) {
  const exact = entries.find((entry) => entry.id === id);
  if (exact) return exact;
  const trigger = schedules
    .flatMap(scheduleHistory)
    .find((run) => run.job === "submit" && `trigger:${run.trigger_id}` === id);
  const submitted = entries.find((entry) => {
    const source = entry.kind === "task" ? entry.task.source.schedule : null;
    return (
      source?.job === "submit" &&
      `trigger:${source.trigger_id}` === id &&
      (!trigger || triggerKey(source) === triggerKey(trigger))
    );
  });
  if (submitted) return submitted;
  const schedule = schedules.find(
    (schedule) =>
      `schedule:${schedule.name}` === id ||
      scheduleHistory(schedule).some(
        (run) => run.job === "submit" && `trigger:${run.trigger_id}` === id,
      ),
  );
  return schedule
    ? entries.find((entry) => entry.schedules.includes(schedule))
    : undefined;
}
