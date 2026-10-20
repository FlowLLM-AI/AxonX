import type { JsonSchema } from "../../shared/schema/types";
export type { TaskStepStatus } from "../../shared/api/event";

export type {
  TaskState,
  ChildTaskRecord,
  ScheduleTrigger,
  TaskSource,
} from "../../shared/api/contracts";
import type { ScheduleRun } from "../../shared/api/contracts";

export interface Schedule {
  scheduler_id: string;
  name: string;
  job: string;
  description: string;
  cron: string;
  timezone: string;
  arguments: Record<string, unknown>;
  concurrency_policy: "allow" | "forbid" | "replace";
  next_run_at: string | null;
  running: number;
  last_trigger: ScheduleRun | null;
  history?: ScheduleRun[];
  history_total?: number;
  history_scheduler_ids?: string[];
}

export type { TaskView as TaskMetadata } from "../../shared/api/contracts";
export type { TaskSummary } from "../../shared/api/contracts";

export type { LogChunk } from "../../shared/api/contracts";

import type { TaskDefinition as DefinitionContract } from "../../shared/api/contracts";
export type TaskDefinition = Omit<
  DefinitionContract,
  "input_schema" | "output_schema"
> & {
  input_schema: JsonSchema;
  output_schema: JsonSchema;
};

export type { TaskHandle } from "../../shared/api/contracts";

export interface TaskRunIdentity {
  task_id: string;
  run_id: string;
  reg_name: string;
  display_name?: string;
}
