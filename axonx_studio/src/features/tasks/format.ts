import { formatDateTime } from "../../shared/lib/format";
import type { Language } from "../../app/types";
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

export function formatDate(value: string | null, language: Language) {
  return formatDateTime(value, language);
}

export function formatDuration(task: TaskStatus, language: Language) {
  if (!task.started_at) return "—";
  const end = task.finished_at
    ? new Date(task.finished_at).getTime()
    : Date.now();
  const seconds = Math.max(
    0,
    Math.floor((end - new Date(task.started_at).getTime()) / 1000),
  );
  if (language === "zh") {
    if (seconds < 60) return `${seconds} 秒`;
    if (seconds < 3600)
      return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
    return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`;
  }
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
