import type { TFunction } from "i18next";
import type {
  TaskDefinition as DefinitionContract,
  TaskMetadata,
  TaskState,
  TaskSummary,
} from "../../shared/api/contracts";
import type { JsonSchema } from "../../shared/schema/values";

export type TaskDefinition = Omit<
  DefinitionContract,
  "input_schema" | "output_schema"
> & {
  input_schema: JsonSchema;
  output_schema: JsonSchema;
};

export interface TaskReference {
  task_id: string;
  started_at: string;
  reg_name: string;
  display_name?: string;
}

export const STATES: TaskState[] = ["running", "failed", "succeeded"];
export type StateFilter = "" | TaskState;
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
    if (filter.state && task.state !== filter.state) continue;
    group.tasks.push(task);
    group.counts[task.state] = (group.counts[task.state] || 0) + 1;
    if (task.state === "running") group.active++;
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

interface TaskStepProgress {
  current: number;
  name: string;
  percentage: number;
}

export function taskStepProgress(
  task: TaskMetadata | TaskSummary,
): TaskStepProgress | null {
  if (!("steps" in task)) {
    const progress = task.step_progress;
    return progress
      ? {
          ...progress,
          percentage: Math.max(
            0,
            Math.min(100, Math.round(progress.percentage ?? 0)),
          ),
        }
      : null;
  }
  const steps = task.steps.filter((step) => !step.parent);
  if (!steps.length) return null;
  const activeIndex = steps.findIndex((step) => !step.finished_at);
  const currentIndex = activeIndex >= 0 ? activeIndex : steps.length - 1;
  const step = steps[currentIndex];
  return {
    current: currentIndex + 1,
    name: step.name,
    percentage: Math.max(0, Math.min(100, Math.round(step.percentage ?? 0))),
  };
}

export function formatDuration(task: TaskMetadata | TaskSummary, t: TFunction) {
  if (!task.started_at) return "—";
  const end = task.finished_at
    ? new Date(task.finished_at).getTime()
    : Date.now();
  const seconds = Math.max(
    0,
    Math.floor((end - new Date(task.started_at).getTime()) / 1000),
  );
  if (seconds < 60) return t("formats.duration.seconds", { seconds });
  if (seconds < 3600)
    return t("formats.duration.minutesSeconds", {
      minutes: Math.floor(seconds / 60),
      seconds: seconds % 60,
    });
  return t("formats.duration.hoursMinutes", {
    hours: Math.floor(seconds / 3600),
    minutes: Math.floor((seconds % 3600) / 60),
  });
}

export const hasTaskReport = (task: TaskMetadata) => Boolean(task.report_kind);
