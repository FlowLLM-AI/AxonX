import type { JsonSchema } from "../schema/values";
import type {
  JobInfo as InfoContract,
  JobResponse as ResponseContract,
} from "./contracts";

export type JobResponse<T = unknown> = Omit<ResponseContract, "answer"> & {
  answer: T;
};
export type JobInfo = Omit<InfoContract, "input_schema" | "output_schema"> & {
  input_schema: JsonSchema;
  output_schema: JsonSchema;
};
export type JobCatalog = Omit<import("./contracts").JobCatalog, "items"> & {
  items: JobInfo[];
};
