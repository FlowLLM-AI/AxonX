export type ResearchKind =
  "analysis" | "backtest" | "etl" | "training" | "predict";
export type ResearchPageId =
  "etl" | "factors" | "training" | "predict" | "backtest";
export type ResearchRow = Record<string, string>;

export interface ArtifactFile {
  path: string;
  bytes?: number;
}

export interface FeatureGroupConfig {
  name?: string;
  label?: string;
  description?: string;
  features?: unknown[];
  columns?: unknown[];
}

export interface ResearchArtifact {
  [key: string]: unknown;
  _path: string;
  _modified?: number;
  task_id: string;
  task_name?: string;
  task_type?: string;
  created_at?: string;
  rows?: number;
  symbols?: number;
  feature_count?: number;
  feature_columns?: string[];
  label_columns?: string[];
  labels?: Record<string, unknown>;
  schema?: Record<string, string>;
  feature_groups?: FeatureGroupConfig[] | Record<string, unknown[]>;
  feature_schema?: {
    title?: string | Record<"zh" | "en", string>;
    groups?: FeatureGroupConfig[] | Record<string, unknown[]>;
  };
  date_range?: { start?: string; end?: string };
  model_target?: string;
  model?: {
    library?: string;
    library_version?: string;
    best_iteration?: number;
  };
  validation_metrics?: { ic_mean?: number; rankic_mean?: number };
  source?: {
    etl_task_id?: string;
    prediction_task_id?: string;
    training_task_id?: string;
  };
  config?: {
    quantiles?: number;
    transaction_cost_rate?: number;
    annual_risk_free_rate?: number;
    annualization_days?: number;
  };
  artifacts?: Record<string, string>;
  artifact_integrity?: Record<string, ArtifactFile>;
}
