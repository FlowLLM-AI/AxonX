import type { JsonSchema } from "../../shared/schema/types";

export interface JobInfo {
  name: string;
  description: string;
  inputSchema: JsonSchema;
  outputSchema: JsonSchema;
}
