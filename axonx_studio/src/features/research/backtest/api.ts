import i18n from "../../../i18n";
import type { RequestOptions } from "../../../shared/api/client";
import { loadParquetRows } from "../../../shared/api/tables";
import { taskDirectory } from "../../../shared/lib/tasks";
import type { BacktestArtifact, DailyRow, SummaryRow } from "./types";

function portfolioArtifact(
  meta: BacktestArtifact,
  portfolio: string,
  role: "daily" | "summary",
) {
  if (meta.output_params.signals_format !== "stock-signals-v3")
    throw new Error(i18n.t("backtest.errors.signalsFormat"));
  const report = meta.output_params.portfolios[Number(portfolio)];
  if (!report) throw new Error(i18n.t("backtest.errors.missingPortfolio"));
  const path = meta.output_params.artifacts[report.artifacts[role]]?.path;
  if (!path) throw new Error(i18n.t("backtest.errors.missingDailySummary"));
  return `${taskDirectory(meta.task_id)}/${path}`;
}

export async function loadBacktest(
  meta: BacktestArtifact,
  portfolio: string,
  options: RequestOptions = {},
) {
  const [daily, summary] = await Promise.all([
    loadParquetRows<DailyRow>(
      portfolioArtifact(meta, portfolio, "daily"),
      options,
    ),
    loadParquetRows<SummaryRow>(
      portfolioArtifact(meta, portfolio, "summary"),
      options,
    ),
  ]);
  return { daily, summary };
}

export async function loadBacktestDaily(
  meta: BacktestArtifact,
  portfolio: string,
  options: RequestOptions = {},
) {
  return loadParquetRows<DailyRow>(
    portfolioArtifact(meta, portfolio, "daily"),
    options,
  );
}
