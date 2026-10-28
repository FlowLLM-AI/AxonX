import type { JobCatalog, JobInfo } from "../shared/api/types";
import contracts from "./job-contracts.json";

export const demoSessionId = "00000000-0000-4000-8000-000000000001";
const defaults: Record<string, unknown> = {
  task_id: "backtest#playground_backtest#demo",
  session_id: demoSessionId,
};
const jobs = contracts.jobs;
const supported: Array<keyof typeof jobs> = [
  "cli",
  "machine_status",
  "list_machines",
  "list_task_defs",
  "get_task_def",
  "list_task_ids",
  "list_task_statuses",
  "status",
  "read_task_log",
  "get_task_graph",
  "stream_task",
  "list_task_directories",
  "list_entries",
  "preview_file",
  "delete_entries",
  "list_agent_sessions",
  "get_agent_session",
  "agent_chat",
  "cancel_agent_turn",
  "rename_agent_session",
  "tag_agent_session",
  "delete_agent_session",
  "fork_agent_session",
];

export const catalog: JobCatalog = {
  items: supported.map((name): JobInfo => {
    const job: JobInfo = jobs[name];
    const properties = Object.fromEntries(
      Object.entries(job.input_schema.properties || {}).map(([key, field]) => [
        key,
        key in defaults ? { ...field, default: defaults[key] } : field,
      ]),
    );
    if (name === "preview_file")
      properties.path = {
        ...properties.path,
        default: "backtest/backtest#playground_backtest#demo/metadata.json",
      };
    if (name === "delete_entries")
      properties.paths = {
        ...properties.paths,
        default: ["backtest/backtest#playground_backtest#volatile"],
      };
    return {
      ...job,
      description: `Browser simulation / 浏览器模拟接口: ${job.description}`,
      input_schema: { ...job.input_schema, properties },
    };
  }),
  total: supported.length,
};
