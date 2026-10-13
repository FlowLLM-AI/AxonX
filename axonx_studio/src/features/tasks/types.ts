import type { DisplayReplica } from "../../shared/lib/replica";
import type { JsonSchema } from "../../shared/schema/types";

export type TaskState =
  "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface TaskStepStatus {
  name: string;
  started_at: string | null;
  finished_at: string | null;
  percentage: number | null;
}

export interface ChildTaskRecord {
  node_name: string;
  attempt: number;
  task: string;
  task_id: string | null;
  run_id: string;
  state: TaskState;
  exit_code: number;
  error: string;
}

export interface ScheduleTrigger {
  name: string;
  job: string;
  trigger_id: string;
  triggered_at: string;
}

export interface TaskSource {
  kind: "submit" | "exec" | "unknown";
  schedule: ScheduleTrigger | null;
}

export interface Schedule {
  name: string;
  job: string;
  description: string;
  cron: string;
  timezone: string;
  arguments: Record<string, unknown>;
  concurrency_policy: "allow" | "forbid" | "replace";
  next_run_at: string | null;
  running: number;
  last_trigger: (ScheduleTrigger & { state: TaskState; error: string }) | null;
}

export interface TaskMetadata {
  task_id: string;
  run_id: string;
  task_type: string;
  reg_name: string;
  source: TaskSource;
  input_params: Record<string, unknown>;
  state: TaskState;
  pid: number | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  steps: TaskStepStatus[];
  children: ChildTaskRecord[];
  output_params: Record<string, unknown>;
  error: string;
  exit_code: number;
  log_path: string;
  replica: DisplayReplica | null;
}

export interface TaskSummary extends Omit<
  TaskMetadata,
  "input_params" | "output_params" | "steps" | "children" | "replica"
> {
  is_replica?: boolean;
  display_name?: string;
  is_online?: boolean;
  step_progress?: {
    current: number;
    total: number;
    name: string;
    percentage: number | null;
  } | null;
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
