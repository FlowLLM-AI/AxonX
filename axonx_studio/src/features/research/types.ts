export type ResearchKind =
  "analysis" | "backtest" | "etl" | "train" | "predict";
export type ResearchPageId =
  "etl" | "factors" | "train" | "predict" | "backtest";

export interface ArtifactFile {
  path: string;
  bytes: number;
  sha256: string;
}

export interface ResearchArtifact {
  _path: string;
  _modified?: number;
  task_key: string;
  created_at: string;
  rows?: number;
  train_rows?: number;
  days?: number;
  model_name?: string;
  feature_columns?: string[];
  label_columns?: string[];
  target_columns?: string[];
  output_columns?: string[];
  prediction_statistics?: {
    days: number;
    symbols: number;
    pred: { mean: number; min: number; median: number; max: number };
    buyable_rows: number;
    valid_return_rows: number;
    candidate_rows: number;
    indices: Record<
      string,
      { constituents: number; days_with_weights: number; null_rows: number }
    >;
  };
  index_weight_columns?: string[];
  scores?: Record<string, Record<string, number>>;
  metrics?: Record<string, number>;
  parameters?: Record<string, unknown>;
  training_curve?: {
    x: string[];
    y: Record<string, number[]>;
  };
  dimensions?: {
    top_ns?: number[];
    holding_detail_top_n?: number;
    benchmarks?: { key: string; label: string }[];
  };
  date_range?: { start?: string; end?: string };
  output_file?: string;
  result_file?: string;
  model_file?: string;
  predictions_file?: string;
  daily_file?: string;
  summary_file?: string;
  source?: string[];
  config: {
    task_id: string;
    task_type: ResearchKind;
    task_name: string;
    include_time: boolean;
    input_dir?: string;
  };
  artifacts: Record<string, ArtifactFile>;
}
