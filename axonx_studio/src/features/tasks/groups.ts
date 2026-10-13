import type { TaskState, TaskSummary } from "./types";

export const ACTIVE = new Set<TaskState>(["queued", "running"]);
export const ATTENTION = new Set<TaskState>(["failed", "cancelled"]);
export const STATES: TaskState[] = [
  "running",
  "queued",
  "failed",
  "cancelled",
  "succeeded",
];
export type StateFilter = "" | "active" | "attention" | TaskState;
export interface TaskGroupData {
  key: string;
  label?: string;
  type: string;
  total: number;
  tasks: TaskSummary[];
  counts: Partial<Record<TaskState, number>>;
  active: number;
}
const timestamp = (task: TaskSummary) => {
  const date = task.started_at || task.created_at || task.finished_at;
  return date ? Date.parse(date) || 0 : 0;
};

export function groupTasks(
  tasks: TaskSummary[],
  filter: { search: string; state: StateFilter; type: string },
): TaskGroupData[] {
  const groups = new Map<string, TaskGroupData>();
  const query = filter.search.trim().toLowerCase();
  for (const task of tasks) {
    const key = task.task_id.split("#").slice(0, 2).join("#");
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        type: task.task_type,
        total: 0,
        tasks: [],
        counts: {},
        active: 0,
      };
      groups.set(key, group);
    }
    group.total++;
    if (filter.type && task.task_type !== filter.type) continue;
    if (
      query &&
      !`${task.task_id} ${task.task_type} ${task.pid ?? ""}`
        .toLowerCase()
        .includes(query)
    )
      continue;
    if (
      filter.state &&
      !(filter.state === "active"
        ? ACTIVE.has(task.state)
        : filter.state === "attention"
          ? ATTENTION.has(task.state)
          : task.state === filter.state)
    )
      continue;
    group.tasks.push(task);
    group.counts[task.state] = (group.counts[task.state] || 0) + 1;
    if (ACTIVE.has(task.state)) group.active++;
  }
  const visible = [...groups.values()].filter((group) => group.tasks.length);
  for (const group of visible)
    group.tasks.sort(
      (a, b) =>
        timestamp(b) - timestamp(a) || a.task_id.localeCompare(b.task_id),
    );
  return visible.sort(
    (a, b) =>
      Number(b.active > 0) - Number(a.active > 0) ||
      timestamp(b.tasks[0]) - timestamp(a.tasks[0]) ||
      a.key.localeCompare(b.key),
  );
}
