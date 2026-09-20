export type ResearchKind =
  "analysis" | "backtest" | "etl" | "train" | "predict";
export type ResearchPageId =
  "etl" | "factors" | "train" | "predict" | "backtest" | "compare";

export interface ArtifactFile {
  path: string;
  size: number;
  sha256: string;
}

/**
 * Training curve protocol: x[i] identifies the same ordered training point
 * in every series. Each named series has exactly x.length finite samples.
 * Series with comparable units and value ranges share y_left; y_right is an
 * optional second range. The chart maps these groups to separate y-axes.
 * A populated curve must have at least one left-axis series, and names must
 * be unique across both groups. Empty x and groups mean no history exists.
 */
export interface TrainingCurveData {
  x: string[];
  y_left: Record<string, number[]>;
  y_right: Record<string, number[]>;
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
  training_curve?: TrainingCurveData;
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
