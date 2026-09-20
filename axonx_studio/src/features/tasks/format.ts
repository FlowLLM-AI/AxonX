import { formatDateTime } from "../../shared/lib/format";
import type { TFunction } from "i18next";
import type { TaskStatus } from "./types";

export interface TaskStepProgress {
  current: number;
  name: string;
  percentage: number;
}

export function taskStepProgress(task: TaskStatus): TaskStepProgress | null {
  if (!task.steps.length) return null;
  const activeIndex = task.steps.findIndex((step) => !step.finished_at);
  const currentIndex = activeIndex >= 0 ? activeIndex : task.steps.length - 1;
  const step = task.steps[currentIndex];
  return {
    current: currentIndex + 1,
    name: step.name,
    percentage: Math.max(0, Math.min(100, Math.round(step.percentage ?? 0))),
  };
}

export function formatDate(value: string | null) {
  return formatDateTime(value);
}

export function formatDuration(task: TaskStatus, t: TFunction) {
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
