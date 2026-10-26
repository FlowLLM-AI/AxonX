import type { JobCatalog } from "../shared/api/types";
import type { JsonSchema } from "../shared/schema/types";

const text = (value: string): JsonSchema => ({
  type: "string",
  default: value,
});
const task = { task_id: text("backtest#demo") };
const session = { session_id: text("demo-session-1") };
const schemas: Record<
  string,
  { input?: Record<string, JsonSchema>; output: string }
> = {
  machine_status: { output: "object" },
  list_machines: { output: "array" },
  list_studio_pages: { output: "array" },
  list_installed_task_definitions: {
    input: { include_schemas: { type: "boolean", default: true } },
    output: "array",
  },
  list_task_statuses: {
    input: {
      detail: { type: "string", enum: ["summary", "full"], default: "summary" },
      task_type: { type: "string" },
      state: {
        type: "string",
        enum: ["running", "succeeded", "failed", "cancelled"],
      },
    },
    output: "array",
  },
  status: {
    input: {
      ...task,
      detail: { type: "string", enum: ["summary", "full"], default: "full" },
    },
    output: "object",
  },
  read_task_log: {
    input: {
      ...task,
      offset: { type: "integer", default: -1 },
      limit: { type: "integer", default: 8192 },
    },
    output: "object",
  },
  get_task_graph: { input: task, output: "object" },
  list_task_directories: {
    input: { task_type: text("backtest") },
    output: "object",
  },
  list_entries: {
    input: {
      path: text(""),
      offset: { type: "integer", minimum: 0, default: 0 },
    },
    output: "object",
  },
  preview_file: {
    input: {
      path: text("backtest/backtest#demo/metadata.json"),
      max_bytes: { type: "integer", minimum: 1, maximum: 33554432 },
      offset: { type: "integer", default: 0 },
      limit: { type: "integer", default: 200 },
    },
    output: "object",
  },
  delete_entries: {
    input: {
      paths: {
        type: "array",
        items: { type: "string" },
        default: ["backtest/backtest#volatile"],
      },
    },
    output: "array",
  },
  list_agent_sessions: { output: "array" },
  get_agent_session: { input: session, output: "object" },
  cancel_agent_turn: { input: session, output: "object" },
  rename_agent_session: {
    input: { ...session, title: text("Demo") },
    output: "object",
  },
  tag_agent_session: {
    input: { ...session, tag: text("demo") },
    output: "object",
  },
  delete_agent_session: { input: session, output: "object" },
  fork_agent_session: { input: session, output: "object" },
};
export const catalog: JobCatalog = {
  items: Object.entries(schemas).map(([name, { input = {}, output }]) => ({
    name,
    description: "Browser simulation / 浏览器模拟接口",
    input_schema: { type: "object", properties: input },
    output_schema: { type: output },
  })),
  total: Object.keys(schemas).length,
};
