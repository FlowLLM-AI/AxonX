import i18n from "../../i18n";
import type { RequestOptions } from "./client";
import { previewWorkspaceFile } from "./workspace";

export async function loadParquetRows<
  T extends Record<string, unknown> = Record<string, unknown>,
>(path: string, options: RequestOptions = {}): Promise<T[]> {
  const pageSize = 5000;
  const rows: T[] = [];
  for (let offset = 0; ; offset += pageSize) {
    options.signal?.throwIfAborted();
    const preview = await previewWorkspaceFile(
      { path, offset, limit: pageSize },
      options,
    );
    options.signal?.throwIfAborted();
    if (preview?.kind !== "parquet")
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

export async function readJsonFile(
  path: string,
  options: RequestOptions = {},
  allowMissing = false,
): Promise<unknown> {
  const preview = await previewWorkspaceFile(
    {
      path,
      offset: 0,
      limit: 1,
      ...(allowMissing ? { allow_missing: true } : {}),
    },
    options,
  );
  options.signal?.throwIfAborted();
  if (preview === null && allowMissing) return undefined;
  if (
    !preview ||
    preview.kind !== "json" ||
    preview.parse_error ||
    preview.truncated
  )
    throw new Error(`Invalid JSON file: ${path}`);
  return preview.data;
}
