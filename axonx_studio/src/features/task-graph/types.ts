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
  missing: boolean;
  root_id?: string;
}

export interface TaskGraphList {
  items: TaskGraphNode[];
  total: number;
  offset: number;
  limit: number;
}

export interface TaskGraph {
  root_id: string;
  selected_id: string;
  nodes: TaskGraphNode[];
  edges: { from: string; to: string }[];
}
