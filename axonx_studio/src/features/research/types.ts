import type {
  BaseAnalysisOutputParams,
  BaseETLOutputParams,
  BasePredictOutputParams,
  BaseTrainOutputParams,
  StockBacktestOutput,
  StockPortfolioOutput,
  TaskMetadata,
} from "../../shared/api/contracts";

export type ResearchKind =
  "analysis" | "backtest" | "etl" | "train" | "predict" | "portfolio";
export type ResearchPageId =
  | "etl"
  | "factors"
  | "train"
  | "predict"
  | "portfolio"
  | "backtest"
  | "compare";

interface PredictionStatistics {
  days?: number;
  symbols?: number;
  pred?: { mean?: number; min?: number; median?: number; max?: number };
  buyable_rows?: number;
  candidate_rows?: number;
  indices?: Record<
    string,
    { constituents: number; days_with_weights: number; null_rows: number }
  >;
}
interface ResearchOutputs {
  analysis: BaseAnalysisOutputParams;
  etl: BaseETLOutputParams;
  train: BaseTrainOutputParams;
  predict: Omit<BasePredictOutputParams, "statistics"> & {
    statistics: PredictionStatistics;
    index_weight_columns?: string[];
  };
  portfolio: StockPortfolioOutput;
  backtest: StockBacktestOutput;
}
/** Discriminated views over the original wire record; no flattened data copy. */
export type ResearchTask<K extends ResearchKind = ResearchKind> = {
  [P in K]: Omit<TaskMetadata, "task_type" | "output_params"> & {
    task_type: P;
    output_params: ResearchOutputs[P];
  };
}[K];
