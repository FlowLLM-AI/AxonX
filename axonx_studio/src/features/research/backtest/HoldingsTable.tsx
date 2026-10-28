import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ListRestart,
  LockKeyhole,
  RotateCcw,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  formatFixed as fixed,
  formatPercent as percent,
} from "../../../shared/lib/format";
import { DataCell as SummaryDataCell } from "../../../shared/ui/DataBar";
import {
  dataBarDomain,
  nextSummarySort,
  valueTone,
  type SummarySort,
} from "./model";
import type { DailyRow, Holding } from "./types";

export function HoldingsPanel({
  row,
  locked,
  onUnlock,
  onLatest,
}: {
  row?: DailyRow;
  locked: boolean;
  onUnlock: () => void;
  onLatest: () => void;
}) {
  const { t, i18n } = useTranslation();
  const holdings = (row?.top30_holdings || []) as Holding[];
  const [sort, setSort] = useState<SummarySort>(null);
  const sortedHoldings = sort
    ? [...holdings].sort((a, b) => {
        const left = a[sort.key as keyof Holding];
        const right = b[sort.key as keyof Holding];
        if (left == null) return right == null ? 0 : 1;
        if (right == null) return -1;
        const comparison =
          typeof left === "number" && typeof right === "number"
            ? left - right
            : String(left).localeCompare(
                String(right),
                i18n.resolvedLanguage === "zh" ? "zh-CN" : "en",
              );
        return comparison * (sort.direction === "asc" ? 1 : -1);
      })
    : holdings;
  const holdingDomain = (key: "prediction" | "daily_return" | "weight") => {
    const values = holdings.map((item) => item[key]);
    return new Set(values).size > 1 ? dataBarDomain(values) : undefined;
  };
  const domains = {
    prediction: holdingDomain("prediction"),
    daily_return: holdingDomain("daily_return"),
    weight: holdingDomain("weight"),
  };
  const holdingHeader = (key: keyof Holding, label: string) => {
    const active = sort?.key === key;
    return (
      <th
        key={key}
        aria-sort={
          active
            ? sort.direction === "asc"
              ? "ascending"
              : "descending"
            : "none"
        }
      >
        <button
          type="button"
          className={`summary-sort-button${active ? " active" : ""}`}
          onClick={() => setSort((current) => nextSummarySort(current, key))}
          aria-label={t("backtest.sortBy", {
            label,
            direction:
              active && sort.direction === "asc"
                ? t("backtest.descending")
                : t("backtest.ascending"),
          })}
        >
          <span>{label}</span>
          {active ? (
            sort.direction === "asc" ? (
              <ArrowUp />
            ) : (
              <ArrowDown />
            )
          ) : (
            <ArrowUpDown />
          )}
        </button>
      </th>
    );
  };
  return (
    <section className="viz-card holdings-panel">
      <header>
        <div>
          <small>TOP 30 HOLDINGS</small>
          <h3>
            {row?.trade_date || "—"} · {holdings.length} {t("backtest.stocks")}
          </h3>
        </div>
        <div className="holdings-actions">
          <button
            type="button"
            className="summary-sort-reset"
            onClick={() => setSort(null)}
            disabled={!sort}
            aria-label={t("backtest.reset_holdings_sorting")}
            title={t("backtest.reset_sorting")}
          >
            <ListRestart />
            {t("backtest.reset_sort")}
          </button>
          {locked && (
            <button type="button" onClick={onUnlock}>
              <LockKeyhole />
              {t("backtest.unlock")}
            </button>
          )}
          <button
            type="button"
            onClick={onLatest}
            title={t("backtest.show_the_latest_day_in")}
          >
            <RotateCcw />
            {t("backtest.latest")}
          </button>
        </div>
      </header>
      <div className="mini-table">
        <table>
          <thead>
            <tr>
              {holdingHeader("rank", "#")}
              {holdingHeader("ts_code", t("backtest.code"))}
              {holdingHeader("name", t("backtest.name"))}
              {holdingHeader("prediction", t("backtest.prediction"))}
              {holdingHeader("daily_return", t("backtest.return"))}
              {holdingHeader("weight", t("backtest.weight"))}
            </tr>
          </thead>
          <tbody>
            {sortedHoldings.map((item) => (
              <tr key={item.ts_code}>
                <td>{item.rank}</td>
                <td>
                  <code>{item.ts_code}</code>
                </td>
                <td>{item.name}</td>
                <td>
                  <SummaryDataCell
                    value={item.prediction}
                    format={(value) => fixed(value, 6)}
                    domain={domains.prediction}
                  />
                </td>
                <td className={valueTone(item.daily_return)}>
                  <SummaryDataCell
                    value={item.daily_return}
                    format={percent}
                    domain={domains.daily_return}
                  />
                </td>
                <td>
                  <SummaryDataCell
                    value={item.weight}
                    format={percent}
                    domain={domains.weight}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
