import { previewWorkspaceFile } from "../../workspace/api";
import type { WorkspacePreview } from "../../workspace/types";
import type {
  BacktestArtifact,
  DailyRow,
  NumericRow,
  SummaryRow,
} from "./types";
import i18n from "../../../i18n";

const rowsOf = <T extends NumericRow>(preview: WorkspacePreview): T[] => {
  if (preview.kind !== "parquet")
    throw new Error(i18n.t("backtest.errors.parquetRequired"));
  const columns = preview.columns || [];
  return (preview.rows || []).map(
    (row) =>
      Object.fromEntries(
        columns.map((column, index) => [column, row[index]]),
      ) as T,
  );
};

const loadParquetRows = async <T extends NumericRow>(
  path: string,
  target?: string,
  signal?: AbortSignal,
): Promise<T[]> => {
  const pageSize = 5000;
  const rows: T[] = [];
  for (let offset = 0; ; offset += pageSize) {
    const preview = await previewWorkspaceFile(
      path,
      offset,
      pageSize,
      target,
      signal,
    );
    if (preview.kind !== "parquet")
      throw new Error(i18n.t("backtest.errors.parquetRequired"));
    rows.push(...rowsOf<T>(preview));
    if (!preview.has_more) return rows;
  }
};

function universeArtifact(
  meta: BacktestArtifact,
  universe: string,
  role: "daily" | "summary",
) {
  if (meta.signals_format !== "stock-signals-v1")
    throw new Error(i18n.t("backtest.errors.signalsFormat"));
  const report = meta.universes?.[universe];
  if (!report) throw new Error(i18n.t("backtest.errors.missingUniverse"));
  const path = meta.artifacts[report.artifacts[role]]?.path;
  if (!path) throw new Error(i18n.t("backtest.errors.missingDailySummary"));
  return `${meta._path}/${path}`;
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
