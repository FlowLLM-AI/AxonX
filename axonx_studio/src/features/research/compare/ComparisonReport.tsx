import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  formatFixed as decimal,
  toNumber as finite,
  formatPercent as percent,
} from "../../../shared/lib/format";
import { Select } from "../../../shared/ui/Select";
import { BacktestChart } from "../backtest/BacktestChart";
import type { ChartRow, ChartSeries, Holding } from "../backtest/types";
import {
  cumulativeSeries,
  holdingOverlap,
  pairedMean,
  pairedRatio,
  periodComparison,
  rollingQuality,
  strategyStats,
  type PairedDay,
  type PeriodUnit,
} from "./model";

type CompareTab = "overview" | "returns" | "periods" | "quality" | "trading";

function ComparisonTable({
  rows,
}: {
  rows: {
    label: string;
    a: number;
    b: number;
    format: (value: number) => string;
  }[];
}) {
  const { t } = useTranslation();
  return (
    <div className="compare-table-wrap">
      <table className="compare-table">
        <thead>
          <tr>
            <th>{t("compare.metric")}</th>
            <th>A</th>
            <th>B</th>
            <th>{t("compare.difference_b_a")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              <td>{row.format(row.a)}</td>
              <td>{row.format(row.b)}</td>
              <td className="compare-difference">
                {row.format(row.b - row.a)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComparisonChart({
  title,
  rows,
  series,
  percentAxis = true,
}: {
  title: string;
  rows: ChartRow[];
  series: ChartSeries[];
  percentAxis?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <section className="viz-card compare-chart-card">
      <header>
        <div>
          <small>{t("compare.common_window")}</small>
          <h3>{title}</h3>
        </div>
      </header>
      <BacktestChart rows={rows} series={series} percent={percentAxis} zoom />
    </section>
  );
}

function drawdownRows(points: PairedDay[], topN: number): ChartRow[] {
  let equityA = 1;
  let equityB = 1;
  let peakA = 1;
  let peakB = 1;
  return points.map((point) => {
    equityA *= 1 + finite(point.a[`top${topN}_net_return`]);
    equityB *= 1 + finite(point.b[`top${topN}_net_return`]);
    peakA = Math.max(peakA, equityA);
    peakB = Math.max(peakB, equityB);
    return { date: point.date, a: equityA / peakA - 1, b: equityB / peakB - 1 };
  });
}

export function ComparisonReport({
  points: visible,
  topN: selectedTopN,
  annualizationDays,
}: {
  points: PairedDay[];
  topN: number;
  annualizationDays: number;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<CompareTab>("overview");
  const [returnMode, setReturnMode] = useState<"net" | "gross">("net");
  const [periodUnit, setPeriodUnit] = useState<PeriodUnit>("year");
  const [qualityKey, setQualityKey] = useState("rank_ic");
  const [holdingDate, setHoldingDate] = useState("");
  const statsA = useMemo(
    () => strategyStats(visible, "a", selectedTopN, annualizationDays),
    [visible, selectedTopN, annualizationDays],
  );
  const statsB = useMemo(
    () => strategyStats(visible, "b", selectedTopN, annualizationDays),
    [visible, selectedTopN, annualizationDays],
  );
  const chartSeries: ChartSeries[] = [
    { key: "a", label: "A" },
    { key: "b", label: "B" },
  ];
  const localizeStart = (rows: ChartRow[]) =>
    rows.map((row) =>
      row.date === "__start__" ? { ...row, date: t("common.start") } : row,
    );

  const tabs: CompareTab[] = [
    "overview",
    "returns",
    "periods",
    "quality",
    "trading",
  ];

  const metricRows = [
    {
      label: t("compare.net_cumulative_return"),
      a: statsA.cumulative,
      b: statsB.cumulative,
      format: percent,
    },
    {
      label: t("compare.net_annualized_return"),
      a: statsA.annualized,
      b: statsB.annualized,
      format: percent,
    },
    {
      label: t("compare.annualized_volatility"),
      a: statsA.volatility,
      b: statsB.volatility,
      format: percent,
    },
    {
      label: t("compare.max_drawdown"),
      a: statsA.maxDrawdown,
      b: statsB.maxDrawdown,
      format: percent,
    },
    {
      label: t("compare.win_rate"),
      a: statsA.winRate,
      b: statsB.winRate,
      format: percent,
    },
    {
      label: t("compare.average_turnover"),
      a: statsA.turnover,
      b: statsB.turnover,
      format: percent,
    },
  ];
  const qualityMetrics = [
    { key: "ic", label: "IC", digits: 4 },
    { key: "rank_ic", label: "RankIC", digits: 4 },
    {
      key: `top${selectedTopN}_ndcg`,
      label: `NDCG@${selectedTopN}`,
      digits: 4,
    },
  ];
  const activeDay =
    visible.find((point) => point.date === holdingDate) || visible.at(-1);
  const holdingsA = (activeDay?.a.top30_holdings || []) as Holding[];
  const holdingsB = (activeDay?.b.top30_holdings || []) as Holding[];
  const overlap = holdingOverlap(holdingsA, holdingsB);

  return (
    <>
      <nav
        className="compare-tabs"
        aria-label={t("compare.comparison_dimensions")}
      >
        {tabs.map((key) => (
          <button
            key={key}
            type="button"
            className={tab === key ? "active" : ""}
            onClick={() => setTab(key)}
          >
            {t(`compare.tabs.${key}`)}
          </button>
        ))}
      </nav>
      {tab === "overview" && (
        <div className="compare-content">
          <div className="compare-kpis">
            {metricRows.slice(0, 4).map((metric) => (
              <article key={metric.label}>
                <small>{metric.label}</small>
                <div>
                  <span>
                    A <strong>{metric.format(metric.a)}</strong>
                  </span>
                  <span>
                    B <strong>{metric.format(metric.b)}</strong>
                  </span>
                </div>
                <em>
                  {t("compare.difference")} {metric.format(metric.b - metric.a)}
                </em>
              </article>
            ))}
          </div>
          <ComparisonChart
            title={t("compare.cumulative_net_return_shared_start")}
            rows={localizeStart(cumulativeSeries(visible, selectedTopN))}
            series={chartSeries}
          />
          <ComparisonTable rows={metricRows} />
        </div>
      )}
      {tab === "returns" && (
        <div className="compare-content">
          <div className="compare-toolbar">
            <span>{t("compare.return_basis")}</span>
            <button
              type="button"
              className={returnMode === "net" ? "active" : ""}
              onClick={() => setReturnMode("net")}
            >
              {t("compare.net")}
            </button>
            <button
              type="button"
              className={returnMode === "gross" ? "active" : ""}
              onClick={() => setReturnMode("gross")}
            >
              {t("compare.gross")}
            </button>
          </div>
          <ComparisonChart
            title={
              returnMode === "net"
                ? t("compare.cumulative_net_return")
                : t("compare.cumulative_gross_return")
            }
            rows={localizeStart(
              cumulativeSeries(visible, selectedTopN, returnMode),
            )}
            series={chartSeries}
          />
          <ComparisonChart
            title={t("compare.net_drawdown")}
            rows={drawdownRows(visible, selectedTopN)}
            series={chartSeries}
          />
          <ComparisonTable rows={metricRows} />
        </div>
      )}
      {tab === "periods" && (
        <div className="compare-content">
          <div className="compare-toolbar">
            <span>{t("compare.period")}</span>
            {(["year", "quarter", "month"] as const).map((unit) => (
              <button
                type="button"
                key={unit}
                className={periodUnit === unit ? "active" : ""}
                onClick={() => setPeriodUnit(unit)}
              >
                {unit === "year"
                  ? t("compare.year")
                  : unit === "quarter"
                    ? t("compare.quarter")
                    : t("compare.month")}
              </button>
            ))}
          </div>
          <div className="compare-table-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  <th>{t("compare.period")}</th>
                  <th>{t("compare.days_2")}</th>
                  <th>A · {t("compare.net_return")}</th>
                  <th>B · {t("compare.net_return")}</th>
                  <th>{t("compare.difference_b_a")}</th>
                </tr>
              </thead>
              <tbody>
                {periodComparison(visible, selectedTopN, periodUnit).map(
                  (row) => (
                    <tr key={row.period}>
                      <th scope="row">{row.period}</th>
                      <td>{row.days}</td>
                      <td>{percent(row.a)}</td>
                      <td>{percent(row.b)}</td>
                      <td>
                        <div className="compare-period-delta">
                          <span
                            style={{
                              width: `${Math.min(100, Math.abs(row.b - row.a) * 250)}%`,
                            }}
                            className={row.b >= row.a ? "positive" : "negative"}
                          />
                          {percent(row.b - row.a)}
                        </div>
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {tab === "quality" && (
        <div className="compare-content">
          <div className="compare-toolbar">
            <span>{t("compare.signal_trend")}</span>
            <Select
              value={qualityKey}
              onChange={(event) => setQualityKey(event.target.value)}
            >
              {qualityMetrics.map((metric) => (
                <option key={metric.key} value={metric.key}>
                  {metric.label}
                </option>
              ))}
            </Select>
          </div>
          <ComparisonChart
            title={`${qualityMetrics.find((metric) => metric.key === qualityKey)?.label || qualityKey} · MA20`}
            rows={rollingQuality(visible, qualityKey)}
            series={chartSeries.map((series) => ({
              ...series,
              format: "precise",
            }))}
            percentAxis={false}
          />
          <ComparisonTable
            rows={[
              ...qualityMetrics.map((metric) => {
                const mean = pairedMean(visible, metric.key);
                return {
                  label: `${metric.label} ${t("compare.mean")}`,
                  a: mean.a,
                  b: mean.b,
                  format: (value: number) => decimal(value, metric.digits),
                };
              }),
              ...(["ic", "rank_ic"] as const).map((key) => {
                const ratio = pairedRatio(visible, key, annualizationDays);
                return {
                  label: key === "ic" ? "ICIR" : "RankICIR",
                  a: ratio.a,
                  b: ratio.b,
                  format: (value: number) => decimal(value, 2),
                };
              }),
            ]}
          />
        </div>
      )}
      {tab === "trading" && (
        <div className="compare-content">
          <ComparisonTable
            rows={[
              metricRows[5],
              {
                label: t("compare.average_daily_cost"),
                a: pairedMean(visible, `top${selectedTopN}_transaction_cost`).a,
                b: pairedMean(visible, `top${selectedTopN}_transaction_cost`).b,
                format: percent,
              },
            ]}
          />
          <ComparisonChart
            title={t("compare.daily_turnover")}
            rows={visible.map((point) => ({
              date: point.date,
              a: point.a[`top${selectedTopN}_turnover`],
              b: point.b[`top${selectedTopN}_turnover`],
            }))}
            series={chartSeries}
          />
          <section className="viz-card compare-holdings">
            <header>
              <div>
                <small>TOP 30 HOLDINGS</small>
                <h3>{t("compare.holdings_comparison")}</h3>
              </div>
              <label>
                {t("compare.trading_day")}
                <Select
                  value={activeDay?.date || ""}
                  onChange={(event) => setHoldingDate(event.target.value)}
                >
                  {visible.map((point) => (
                    <option key={point.date} value={point.date}>
                      {point.date}
                    </option>
                  ))}
                </Select>
              </label>
            </header>
            <div className="compare-overlap">
              <strong>
                {t("compare.shared_holdings")} {overlap.common.length}
              </strong>
              <span>
                {t("compare.overlap")} {percent(overlap.ratio)}
              </span>
              <span>
                A {t("compare.only")} {overlap.onlyA.length}
              </span>
              <span>
                B {t("compare.only")} {overlap.onlyB.length}
              </span>
            </div>
            <div className="compare-holdings-grid">
              {([holdingsA, holdingsB] as const).map((holdings, index) => (
                <div key={index}>
                  <h4>{index === 0 ? "A" : "B"} · Top 30</h4>
                  <div className="compare-table-wrap">
                    <table className="compare-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>{t("compare.code")}</th>
                          <th>{t("compare.name")}</th>
                          <th>{t("compare.daily_return")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {holdings.map((item) => (
                          <tr
                            key={item.ts_code}
                            className={
                              overlap.common.includes(item.ts_code)
                                ? "shared"
                                : ""
                            }
                          >
                            <td>{item.rank}</td>
                            <td>
                              <code>{item.ts_code}</code>
                            </td>
                            <td>{item.name}</td>
                            <td>{percent(item.daily_return)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
