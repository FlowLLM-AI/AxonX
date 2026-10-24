import type { JsonSchema } from "../../shared/schema/types";
export type { TaskStepStatus } from "../../shared/api/event";

export type {
  TaskState,
  ChildTaskRecord,
  TaskSource,
} from "../../shared/api/contracts";

export type { TaskMetadata } from "../../shared/api/contracts";
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

export interface TaskRunIdentity {
  task_id: string;
  run_id: string;
  reg_name: string;
  display_name?: string;
}
