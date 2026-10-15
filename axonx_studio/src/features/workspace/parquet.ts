import i18n from "../../i18n";
import { previewWorkspaceFile } from "./api";

export async function loadParquetRows<
  T extends Record<string, unknown> = Record<string, unknown>,
>(path: string, target?: string, signal?: AbortSignal): Promise<T[]> {
  const pageSize = 5000;
  const rows: T[] = [];
  for (let offset = 0; ; offset += pageSize) {
    signal?.throwIfAborted();
    const preview = await previewWorkspaceFile(
      path,
      offset,
      pageSize,
      target,
      signal,
    );
    signal?.throwIfAborted();
    if (preview.kind !== "parquet")
      throw new Error(i18n.t("backtest.errors.parquetRequired"));
    rows.push(
      ...preview.rows.map(
        (row) =>
          Object.fromEntries(
            preview.columns.map((column, index) => [column, row[index]]),
          ) as T,
      ),
    );
    if (!preview.has_more) return rows;
  }
}
