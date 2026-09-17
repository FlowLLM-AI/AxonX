import { previewWorkspaceFile } from "../../workspace/api";
import type { WorkspacePreview } from "../../../types";
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
    previewWorkspaceFile(
      `${meta._path}/${daily}`,
      0,
      200,
      remoteIp,
      true,
      signal,
    ),
    previewWorkspaceFile(
      `${meta._path}/${summary}`,
      0,
      200,
      remoteIp,
      true,
      signal,
    ),
  ]);
  return {
    daily: rowsOf<DailyRow>(dailyPreview),
    summary: rowsOf<SummaryRow>(summaryPreview),
  };
}

export async function loadBacktestDaily(
  meta: BacktestArtifact,
  remoteIp?: string,
  signal?: AbortSignal,
) {
  const daily = meta.artifacts?.daily?.path;
  if (!daily) throw new Error("回测 metadata 缺少 daily 产物");
  const preview = await previewWorkspaceFile(
    `${meta._path}/${daily}`,
    0,
    200,
    remoteIp,
    true,
    signal,
  );
  return rowsOf<DailyRow>(preview);
}
