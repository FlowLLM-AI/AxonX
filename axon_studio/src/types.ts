export type Language = "zh" | "en";
export type ThemePreference = "light" | "dark" | "system";
export type PageId = "machines" | "tasks" | "submit" | "rawData" | "factors" | "training" | "prediction" | "backtest";
export type TaskState = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface TaskStepStatus {
  name: string;
  started_at: string | null;
  finished_at: string | null;
  percentage: number | null;
}

export interface TaskStatus {
  task_id: string;
  task_type: string;
  state: TaskState;
  pid: number | null;
  started_at: string | null;
  finished_at: string | null;
  steps: TaskStepStatus[];
  result: Record<string, unknown>;
  error: string;
  exit_code: number;
  log_path: string;
}

export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  anyOf?: JsonSchema[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  format?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
}

export interface TaskInfo {
  name: string;
  task_type: string;
  description: string;
  config_schema: JsonSchema;
  output_keys: string[];
}

export interface ApiResponse<T> {
  answer: T;
  success: boolean;
  metadata: Record<string, unknown>;
}

export interface CpuInfo {
  total_cores: number;
  physical_cores: number | null;
  usage_percent: number;
  used_cores: number;
}

export interface MemoryInfo {
  total_bytes: number;
  used_bytes: number;
  available_bytes: number;
  usage_percent: number;
}

export interface GpuInfo {
  vendor: string;
  index: number;
  uuid: string | null;
  name: string | null;
  memory_total_bytes: number | null;
  memory_used_bytes: number | null;
  memory_available_bytes: number | null;
  memory_usage_percent: number | null;
  usage_percent: number | null;
}

export interface MachineInfo {
  axonx: { version: string; git_commit: string | null };
  cpu: CpuInfo;
  memory: MemoryInfo;
  gpus: GpuInfo[] | null;
}

export interface MachineNode {
  id: string;
  address: string;
  isLocal: boolean;
  healthy: boolean;
  info?: MachineInfo;
}
