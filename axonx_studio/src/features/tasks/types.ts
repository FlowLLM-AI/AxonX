import type { JsonSchema } from "../../shared/schema/types";

export type TaskState =
  "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface TaskStepStatus {
  name: string;
  started_at: string | null;
  finished_at: string | null;
  percentage: number | null;
}

export interface TaskStatus {
  task_id: string;
  run_id: string;
  task_type: string;
  task_name: string;
  config: Record<string, unknown>;
  state: TaskState;
  pid: number | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  steps: TaskStepStatus[];
  result: Record<string, unknown>;
  error: string;
  exit_code: number;
  log_path: string;
}

export interface TaskLogChunk {
  content: string;
  start_offset: number;
  next_offset: number;
  file_size: number;
  has_more_before: boolean;
  has_more_after: boolean;
  reset: boolean;
  channel?: string;
}

export interface TaskDefinition {
  name: string;
  source: "native" | "plugin";
  plugin?: string | null;
  task_type: string;
  description: string;
  input_schema: JsonSchema;
  output_schema: JsonSchema;
}

export interface TaskHandle {
  task_id: string;
  run_id: string;
  task: string;
}
