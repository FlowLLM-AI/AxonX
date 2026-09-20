import type { JsonSchema } from "../schema/types";

export interface JobResponse<T = unknown> {
  answer: T;
  success: boolean;
  metadata: Record<string, unknown>;
}

export interface JobInfo {
  name: string;
  description: string;
  input_schema: JsonSchema;
  output_schema: JsonSchema;
}

export interface JobCatalog {
  items: JobInfo[];
  total: number;
}
