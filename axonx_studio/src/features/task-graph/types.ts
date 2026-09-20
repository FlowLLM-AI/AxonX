export type TaskKind =
  | "base"
  | "api"
  | "etl"
  | "analysis"
  | "train"
  | "predict"
  | "inference"
  | "backtest";

export interface TaskGraphNode {
  task_id: string;
  kind: TaskKind;
  task_name: string | null;
  created_at: string | null;
  parent_ids: string[];
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled" | null;
  missing: boolean;
  provisional: boolean;
}

export interface TaskGraph {
  root_id: string;
  selected_id: string;
  nodes: TaskGraphNode[];
  edges: { from: string; to: string }[];
}
