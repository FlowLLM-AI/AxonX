import { ArrowDown, ArrowUp, ArrowUpDown, RotateCcw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  formatFixed as fixed,
  toNumber as number,
  formatPercent as percent,
} from "../../../shared/lib/format";
import { DataCell as SummaryDataCell } from "../../../shared/ui/DataBar";
import { Select } from "../../../shared/ui/Select";
import {
  dataBarDomain,
  metricValue,
  nextSummarySort,
  performanceMetrics,
  signalMetrics,
  valueTone,
  type SummaryMetric,
  type SummarySort,
} from "./model";
import type { BenchmarkDefinition, SummaryRow } from "./types";

export function SummaryView({
  rows,
  topNs,
  benchmarks,
}: {
  rows: SummaryRow[];
  topNs: number[];
  benchmarks: BenchmarkDefinition[];
}) {
  const { t } = useTranslation();
  const [topN, setTopN] = useState(topNs.includes(30) ? 30 : topNs[0]);
  const [signalSort, setSignalSort] = useState<SummarySort>(null);
  const [detailSort, setDetailSort] = useState<SummarySort>(null);
  const overall = rows[0]?.period_type === "overall";
  const periods = [...rows].sort((a, b) => a.period.localeCompare(b.period));
  const metrics: SummaryMetric[] = [
    ...performanceMetrics,
    ...benchmarks.flatMap(({ key, label }) => [
      {
        key: `information_ratio_${key}`,
        label: `IR · ${label}`,
        format: fixed,
        percent: false,
      },
      {
        key: `net_relative_max_drawdown_${key}`,
        label: `${t("backtest.net_relative_max_drawdown")} · ${label}`,
        format: percent,
        percent: true,
      },
    ]),
  ];
  const periodName = (row: SummaryRow) =>
    overall ? `${row.period_start}—${row.period_end}` : row.period;
  if (!rows.length)
    return <div className="chart-empty">{t("backtest.noSummaryData")}</div>;
  const detailRows = overall
    ? topNs.map((n) => ({ row: periods[0], topN: n, key: `top-${n}` }))
    : periods.map((row) => ({ row, topN, key: row.period }));
  const signalDomains = Object.fromEntries(
    signalMetrics.map(({ key }) => [
      key,
      dataBarDomain(periods.map((row) => row[key])),
    ]),
  );
  const detailDomains = Object.fromEntries(
    metrics.map(({ key }) => [
      key,
      dataBarDomain(
        detailRows.map(({ row, topN: n }) => metricValue(row, n, key)),
      ),
    ]),
  );
  const sortedSignalRows = signalSort
    ? [...periods].sort((a, b) => {
        const { key, direction } = signalSort;
        if (key === "period") {
          return (
            a.period.localeCompare(b.period) * (direction === "asc" ? 1 : -1)
          );
        }
        const left = number(a[key]);
        const right = number(b[key]);
        if (!Number.isFinite(left)) return Number.isFinite(right) ? 1 : 0;
        if (!Number.isFinite(right)) return -1;
        return (left - right) * (direction === "asc" ? 1 : -1);
      })
    : periods;
  const sortedDetailRows = detailSort
    ? [...detailRows].sort((a, b) => {
        const { key, direction } = detailSort;
        if (key === "top_n") {
          return (a.topN - b.topN) * (direction === "asc" ? 1 : -1);
        }
        if (key === "period") {
          return (
            a.row.period.localeCompare(b.row.period) *
            (direction === "asc" ? 1 : -1)
          );
        }
        const left = number(metricValue(a.row, a.topN, key));
        const right = number(metricValue(b.row, b.topN, key));
        if (!Number.isFinite(left)) return Number.isFinite(right) ? 1 : 0;
        if (!Number.isFinite(right)) return -1;
        return (left - right) * (direction === "asc" ? 1 : -1);
      })
    : detailRows;
  const sortHeader = (
    key: string,
    label: string,
    sort: SummarySort,
    onSort: (key: string) => void,
  ) => {
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
          onClick={() => onSort(key)}
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
  const topNControl = (
    <label className="summary-select-label">
      <span>Top N</span>
      <Select
        aria-label={t("backtest.select_top_n")}
        value={topN}
        onChange={(event) => setTopN(Number(event.target.value))}
      >
        {topNs.map((n) => (
          <option key={n} value={n}>
            Top {n}
          </option>
        ))}
      </Select>
    </label>
  );
  return (
    <div className="summary-view">
      <section className="summary-section">
        <div className="summary-section-heading">
          <span className="summary-section-index">01</span>
          <div>
            <small>{t("backtest.independent_of_top_n")}</small>
            <h3>{t("backtest.overall_metrics")}</h3>
          </div>
        </div>
        {overall && (
          <div className="summary-signal-cards">
            {signalMetrics.map(({ key, format }) => (
              <article key={key} className="viz-card">
                <span>{t(`backtest.metrics.${key}`)}</span>
                <strong>{format(rows[0][key])}</strong>
              </article>
            ))}
          </div>
        )}
        <section className="viz-card summary-table summary-signal-table">
          <header>
            <div>
              <small>BASE METRICS</small>
              <h3>{t("backtest.overall_metric_details")}</h3>
            </div>
            <button
              type="button"
              className="summary-sort-reset"
              onClick={() => setSignalSort(null)}
              disabled={!signalSort}
              aria-label={t("backtest.reset_overall_metric_sorting")}
              title={t("backtest.reset_sorting")}
            >
              <RotateCcw />
            </button>
          </header>
          <div
            className="mini-table"
            role="region"
            aria-label={t("backtest.overall_metric_details")}
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  {sortHeader(
                    "period",
                    t("backtest.period"),
                    signalSort,
                    (key) =>
                      setSignalSort((current) => nextSummarySort(current, key)),
                  )}
                  {signalMetrics.map((metric) =>
                    sortHeader(
                      metric.key,
                      t(`backtest.metrics.${metric.key}`),
                      signalSort,
                      (key) =>
                        setSignalSort((current) =>
                          nextSummarySort(current, key),
                        ),
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {sortedSignalRows.map((row) => (
                  <tr key={row.period}>
                    <td>
                      <strong>{periodName(row)}</strong>
                    </td>
                    {signalMetrics.map(({ key, format }) => (
                      <td key={key}>
                        <SummaryDataCell
                          value={row[key]}
                          format={format}
                          domain={
                            periods.length > 1 ? signalDomains[key] : undefined
                          }
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
      <section className="summary-section">
        <div className="summary-section-heading">
          <span className="summary-section-index">02</span>
          <div>
            <small>{t("backtest.filter_by_portfolio_size")}</small>
            <h3>Top N {t("backtest.metrics_2")}</h3>
          </div>
        </div>
        <section className="viz-card summary-table summary-detail-table">
          <header>
            <div>
              <small>TOP N DETAIL</small>
              <h3>
                {overall
                  ? t("backtest.all_top_n_metrics")
                  : t("backtest.topNAllMetrics", { topN })}
              </h3>
            </div>
            <div className="summary-chart-controls">
              {!overall && topNControl}
              <span className="summary-table-hint">
                {t("backtest.scroll_sideways")}
              </span>
              <button
                type="button"
                className="summary-sort-reset"
                onClick={() => setDetailSort(null)}
                disabled={!detailSort}
                aria-label={t("backtest.reset_table_sorting")}
                title={t("backtest.reset_sorting")}
              >
                <RotateCcw />
              </button>
            </div>
          </header>
          <div
            className="mini-table"
            role="region"
            aria-label={
              overall
                ? t("backtest.overall_metrics_by_top_n")
                : t("backtest.top_n_period_metric_details")
            }
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  {sortHeader(
                    overall ? "top_n" : "period",
                    overall ? "Top N" : t("backtest.period"),
                    detailSort,
                    (key) =>
                      setDetailSort((current) => nextSummarySort(current, key)),
                  )}
                  {metrics.map((metric) =>
                    sortHeader(
                      metric.key,
                      metric.label ?? t(`backtest.metrics.${metric.key}`),
                      detailSort,
                      (key) =>
                        setDetailSort((current) =>
                          nextSummarySort(current, key),
                        ),
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {sortedDetailRows.map(({ row, topN: n, key }) => (
                  <tr key={key}>
                    <td>
                      <strong>{overall ? `Top ${n}` : periodName(row)}</strong>
                    </td>
                    {metrics.map(({ key, format }) => {
                      const value = metricValue(row, n, key);
                      return (
                        <td key={key} className={valueTone(value)}>
                          <SummaryDataCell
                            value={value}
                            format={format}
                            domain={
                              detailRows.length > 1
                                ? detailDomains[key]
                                : undefined
                            }
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </div>
  );
}
