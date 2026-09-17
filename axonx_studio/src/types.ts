export type Language = "zh" | "en";
export type ThemePreference = "light" | "dark" | "system";

export interface ContextOption {
  value: string;
  label: string;
  detail?: string;
}

export type PageId =
  | "home"
  | "machines"
  | "tasks"
  | "submit"
  | "datasets"
  | "etl"
  | "files"
  | "factors"
  | "train"
  | "models"
  | "inference"
  | "predict"
  | "strategies"
  | "backtest"
  | "reports"
  | "plugins"
  | "jobs"
  | "taskCatalog"
  | "components";

export type { ApiResponse } from "./shared/api/types";
export type { JsonSchema } from "./shared/schema/types";
export type { JobInfo } from "./features/api-catalog/types";
export type {
  CpuInfo,
  GpuInfo,
  MachineInfo,
  MachineNode,
  MemoryInfo,
} from "./features/machines/types";
export type {
  TaskDefinition,
  TaskLogChunk,
  TaskState,
  TaskStatus,
  TaskStepStatus,
} from "./features/tasks/types";
export type {
  WorkspaceDirectory,
  WorkspaceEntry,
  WorkspaceEntryKind,
  WorkspacePreview,
  WorkspacePreviewKind,
} from "./features/workspace/types";
