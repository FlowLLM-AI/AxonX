export type ThemePreference = "light" | "dark" | "system";
export type PageId =
  | "home"
  | "machines"
  | "tasks"
  | "submit"
  | "datasets"
  | "etl"
  | "files"
  | "factors"
  | "train"
  | "models"
  | "inference"
  | "predict"
  | "strategies"
  | "backtest"
  | "reports"
  | "plugins"
  | "jobs"
  | "taskCatalog"
  | "components";

export interface ContextOption {
  value: string;
  label: string;
  detail?: string;
}
