import { useState } from "react";
import { useTranslation } from "react-i18next";
import { DataBar } from "../../shared/ui/DataBar";
import {
  filterSignalUniverse,
  missingUniverseContext,
  parseUniverse,
  signalUniverses,
  type SignalUniverse,
} from "./signalUniverse";
import { display } from "./format";
import { ReportTable, type Column } from "./ReportTable";

export interface SignalFilters {
  poolKey?: string;
  buyableOnly: boolean;
}

export function SignalTable({
  rows,
  previous,
  scoreMethod = "mean",
  recordedUniverse,
  filters,
  onFiltersChange,
}: {
  rows: Record<string, unknown>[];
  previous: Record<string, unknown>[];
  scoreMethod?: string;
  recordedUniverse?: unknown;
  filters?: SignalFilters;
  onFiltersChange?: (filters: SignalFilters) => void;
}) {
  const { t } = useTranslation();
  const [localFilters, setLocalFilters] = useState<SignalFilters>({
    buyableOnly: true,
  });
  const currentFilters = filters ?? localFilters;
  const setFilters = onFiltersChange ?? setLocalFilters;
  const { buyableOnly } = currentFilters;
  const recorded = parseUniverse(recordedUniverse);
  const poolKey = currentFilters.poolKey ?? recorded?.key ?? "all";
  const pools =
    recorded && !signalUniverses.some((p) => p.key === recorded.key)
      ? [...signalUniverses, recorded]
      : signalUniverses;
  const pool = pools.find((p) => p.key === poolKey) || pools[0];
  const missing = missingUniverseContext(rows, pool);
  const poolRows = missing ? [] : filterSignalUniverse(rows, pool, buyableOnly);
  const previousRanks = new Map(
    filterSignalUniverse(previous, pool, true).map((row, index) => [
      row.ts_code,
      index + 1,
    ]),
  );
  const poolRanks = new Map(
    filterSignalUniverse(rows, pool, true).map((row, index) => [
      row.ts_code,
      index + 1,
    ]),
  );
  const poolLabel = (p: SignalUniverse) =>
    p.kind === "all"
      ? t("onlineReport.pools.all")
      : p.kind === "index"
        ? p.index_codes!.map((c) => t(`onlineReport.pools.${c}`)).join(" + ")
        : t(`onlineReport.pools.${p.field}`, { percent: p.top_percent });
  const scored = rows.map(
    (row): Record<string, unknown> & { score_mean: number | null } => {
      const seeds = Object.entries(row)
        .filter(
          ([key, value]) =>
            key.startsWith("pred_seed_") &&
            typeof value === "number" &&
            Number.isFinite(value),
        )
        .map(([, value]) => value as number);
      const mean = seeds.length
        ? seeds.reduce((sum, value) => sum + value, 0) / seeds.length
        : scoreMethod === "mean" &&
            typeof row.pred === "number" &&
            Number.isFinite(row.pred)
          ? row.pred
          : null;
      return {
        ...row,
        score_mean: mean,
        score_std: seeds.length
          ? Math.sqrt(
              seeds.reduce((sum, value) => sum + (value - mean!) ** 2, 0) /
                seeds.length,
            )
          : null,
      };
    },
  );
  const domain = scored.reduce(
    (range, row) => ({
      min: Math.min(range.min, row.score_mean ?? 0),
      max: Math.max(range.max, row.score_mean ?? 0),
    }),
    { min: 0, max: 0 },
  );
  const visibleCodes = new Set(poolRows.map((row) => row.ts_code));
  const selected = scored
    .filter((row) => visibleCodes.has(row.ts_code))
    .map((row) => ({
      ...row,
      pool_rank: poolRanks.get(row.ts_code) ?? null,
      rank_change:
        poolRanks.has(row.ts_code) && previousRanks.has(row.ts_code)
          ? previousRanks.get(row.ts_code)! - poolRanks.get(row.ts_code)!
          : null,
    }));
  const fields: [string, Column["format"]?][] = [
    ["pool_rank", "integer"],
    ["rank", "integer"],
    ["ts_code"],
    ["name"],
    ...(scoreMethod === "mean"
      ? []
      : [["pred", "score"] as [string, Column["format"]]]),
    ["score_mean", "score"],
    ["rank_change", "integer"],
    ["is_buyable_at_signal", "boolean"],
    ["signal_price", "score"],
  ];
  return (
    <>
      {(!recorded || missing) && (
        <p className="online-warning" role="status">
          {t(
            !recorded
              ? "onlineReport.unknownPool"
              : "onlineReport.missingPoolContext",
          )}
        </p>
      )}
      <ReportTable
        rows={selected}
        defaultSort="pool_rank"
        actions={
          <div className="online-signal-toolbar">
            <label className="online-pool-picker">
              {t("backtest.universe")}
              <select
                aria-label={t("backtest.universe")}
                value={pool.key}
                onChange={(e) =>
                  setFilters({ ...currentFilters, poolKey: e.target.value })
                }
              >
                {pools.map((p) => (
                  <option
                    key={p.key}
                    value={p.key}
                    disabled={missingUniverseContext(rows, p)}
                  >
                    {poolLabel(p)}
                    {p.key === recorded?.key
                      ? ` · ${t("onlineReport.recordedPool")}`
                      : ""}
                  </option>
                ))}
              </select>
            </label>
            {recorded && pool.key !== recorded.key && (
              <small>
                {t("onlineReport.viewPoolOnly", { pool: poolLabel(recorded) })}
              </small>
            )}
            <label className="online-checkbox">
              <input
                type="checkbox"
                checked={buyableOnly}
                onChange={(event) =>
                  setFilters({
                    ...currentFilters,
                    buyableOnly: event.target.checked,
                  })
                }
              />
              {t("onlineReport.buyableOnly")}
            </label>
          </div>
        }
        columns={[
          ...fields.map(([key, format]) => ({
            key,
            format,
            label: t(
              `onlineReport.columns.${key === "score_mean" ? "score_summary" : key === "rank" ? "original_rank" : key}`,
            ),
            ...(key === "score_mean"
              ? {
                  render: (row: Record<string, unknown>) => (
                    <DataBar
                      value={
                        typeof row.score_mean === "number"
                          ? row.score_mean
                          : NaN
                      }
                      domain={domain}
                    >
                      {display(row.score_mean, "score")}
                      <small className="online-score-deviation">
                        {" "}
                        ± {display(row.score_std, "score")}
                      </small>
                    </DataBar>
                  ),
                }
              : {}),
          })),
        ]}
      />
    </>
  );
}
