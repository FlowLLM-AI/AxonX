import { previewWorkspaceFile } from "../../workspace/api";
import type { WorkspacePreview } from "../../workspace/types";
import type {
  BacktestArtifact,
  DailyRow,
  NumericRow,
  SummaryRow,
} from "./types";

const rowsOf = <T extends NumericRow>(preview: WorkspacePreview): T[] => {
  if (preview.kind !== "parquet")
    throw new Error("回测产物必须是 Parquet 文件");
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
  remoteIp?: string,
  signal?: AbortSignal,
): Promise<T[]> => {
  const pageSize = 5000;
  const rows: T[] = [];
  for (let offset = 0; ; offset += pageSize) {
    const preview = await previewWorkspaceFile(
      path,
      offset,
      pageSize,
      remoteIp,
      signal,
    );
    if (preview.kind !== "parquet")
      throw new Error("回测产物必须是 Parquet 文件");
    rows.push(...rowsOf<T>(preview));
    if (!preview.has_more) return rows;
  }
};

export async function loadBacktest(
  meta: BacktestArtifact,
  remoteIp?: string,
  signal?: AbortSignal,
) {
  const daily = meta.artifacts?.daily?.path;
  const summary = meta.artifacts?.summary?.path;
  if (!daily || !summary)
    throw new Error("回测 metadata 缺少 daily 或 summary 产物");
  const [dailyPreview, summaryPreview] = await Promise.all([
    loadParquetRows<DailyRow>(`${meta._path}/${daily}`, remoteIp, signal),
    loadParquetRows<SummaryRow>(`${meta._path}/${summary}`, remoteIp, signal),
  ]);
  return {
    daily: dailyPreview,
    summary: summaryPreview,
  };
}

export async function loadBacktestDaily(
  meta: BacktestArtifact,
  remoteIp?: string,
  signal?: AbortSignal,
) {
  const daily = meta.artifacts?.daily?.path;
  if (!daily) throw new Error("回测 metadata 缺少 daily 产物");
  return loadParquetRows<DailyRow>(`${meta._path}/${daily}`, remoteIp, signal);
}
