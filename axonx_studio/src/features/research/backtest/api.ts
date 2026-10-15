import { taskDirectory } from "../../../shared/lib/tasks";
import i18n from "../../../i18n";
import { loadParquetRows } from "../../workspace/parquet";
import type { BacktestArtifact, DailyRow, SummaryRow } from "./types";

function universeArtifact(
  meta: BacktestArtifact,
  universe: string,
  role: "daily" | "summary",
) {
  if (meta.output_params.signals_format !== "stock-signals-v1")
    throw new Error(i18n.t("backtest.errors.signalsFormat"));
  const report = meta.output_params.universes?.[universe];
  if (!report) throw new Error(i18n.t("backtest.errors.missingUniverse"));
  const path = meta.output_params.artifacts[report.artifacts[role]]?.path;
  if (!path) throw new Error(i18n.t("backtest.errors.missingDailySummary"));
  return `${taskDirectory(meta.task_id)}/${path}`;
}

export async function loadBacktest(
  meta: BacktestArtifact,
  universe: string,
  target?: string,
  signal?: AbortSignal,
) {
  const [daily, summary] = await Promise.all([
    loadParquetRows<DailyRow>(
      universeArtifact(meta, universe, "daily"),
      target,
      signal,
    ),
    loadParquetRows<SummaryRow>(
      universeArtifact(meta, universe, "summary"),
      target,
      signal,
    ),
  ]);
  return { daily, summary };
}

export async function loadBacktestDaily(
  meta: BacktestArtifact,
  universe: string,
  target?: string,
  signal?: AbortSignal,
) {
  return loadParquetRows<DailyRow>(
    universeArtifact(meta, universe, "daily"),
    target,
    signal,
  );
}
