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
  list_installed_task_definitions: { output: "array" },
  list_task_statuses: { output: "array" },
  status: { input: task, output: "object" },
  cancel: { input: task, output: "boolean" },
  read_task_log: {
    input: {
      ...task,
      offset: { type: "integer", default: -1 },
      limit: { type: "integer", default: 65536 },
    },
    output: "object",
  },
  get_task_graph: { input: task, output: "object" },
  submit: {
    input: {
      task: text("playground.backtest"),
      strategy: {
        type: "string",
        enum: ["steady", "volatile"],
        default: "steady",
      },
      outcome: {
        type: "string",
        enum: ["success", "failure"],
        default: "success",
      },
    },
    output: "object",
  },
  delete_tasks: {
    input: {
      task_ids: {
        type: "array",
        items: { type: "string" },
        default: ["train#failed"],
      },
    },
    output: "array",
  },
  list_task_runs: { input: { task_type: text("backtest") }, output: "object" },
  list_entries: { input: { path: text("tushare") }, output: "object" },
  preview_file: {
    input: {
      path: text("runs/backtest#demo/metadata.json"),
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
        default: ["runs/backtest#volatile"],
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
