import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { BacktestChart } from "../research/backtest/BacktestChart";
import { DateRangeSlider } from "../research/backtest/DateRangeSlider";
import type { ChartSeries } from "../research/backtest/types";
import { ReportTable } from "./ReportTable";
import { performanceRows } from "./curves";

export function Performance({
  rows,
  summary,
  topN,
  benchmarks,
}: {
  rows: Record<string, unknown>[];
  summary: Record<string, unknown>[];
  topN: number;
  benchmarks: { key: string; label: string }[];
}) {
  const { t } = useTranslation();
  const [range, setRange] = useState<[number, number]>([
    0,
    Math.max(0, rows.length - 1),
  ]);
  const selected = useMemo(
    () => rows.slice(range[0], range[1] + 1),
    [rows, range],
  );
  const chartRows = useMemo(
    () => performanceRows(selected, topN, benchmarks),
    [selected, topN, benchmarks],
  );
  const series: ChartSeries[] = [
    { key: "net", label: `Top ${topN}`, format: "percent" },
    ...benchmarks.map(({ key, label }) => ({
      key,
      label,
      dashed: true,
      format: "percent" as const,
    })),
  ];
  if (!rows.length)
    return <div className="empty-state">{t("onlineReport.noRows")}</div>;
  return (
    <div className="online-performance">
      <div className="online-date-range">
        <span>{selected[0]?.trade_date as string}</span>
        <DateRangeSlider
          range={range}
          count={rows.length}
          labels={[t("backtest.dateRange.start"), t("backtest.dateRange.end")]}
          onChange={(edge, value) =>
            setRange(
              edge === 0
                ? [Math.min(value, range[1]), range[1]]
                : [range[0], Math.max(value, range[0])],
            )
          }
        />
        <span>{selected.at(-1)?.trade_date as string}</span>
      </div>
      <section className="viz-card">
        <header>
          <p className="eyebrow">FORWARD PERFORMANCE</p>
          <h3>{t("onlineReport.netReturn")}</h3>
          <small>{t("onlineReport.performanceHint")}</small>
        </header>
        <BacktestChart rows={chartRows} series={series} percent zoom />
      </section>
      <div className="online-chart-grid">
        <section className="viz-card">
          <h3>{t("onlineReport.drawdown")}</h3>
          <BacktestChart
            rows={chartRows}
            series={[
              {
                key: "drawdown",
                label: t("onlineReport.drawdown"),
                format: "percent",
              },
            ]}
            percent
          />
        </section>
        <section className="viz-card">
          <h3>{t("onlineReport.turnoverCosts")}</h3>
          <BacktestChart
            rows={chartRows}
            series={[
              {
                key: `top${topN}_turnover`,
                label: t("onlineReport.turnover"),
                format: "percent",
              },
              {
                key: `top${topN}_transaction_cost`,
                label: t("onlineReport.cost"),
                format: "percent",
                axis: 1,
              },
            ]}
            percent
          />
        </section>
      </div>
      <h3>{t("onlineReport.dailyLedger")}</h3>
      <ReportTable
        rows={selected}
        columns={[
          { key: "trade_date", label: t("onlineReport.signalDate") },
          ...["net_return", "turnover", "transaction_cost", "cash_weight"].map(
            (key) => ({
              key: `top${topN}_${key}`,
              label: t(`onlineReport.columns.${key}`),
              format: "percent" as const,
            }),
          ),
        ]}
      />
      <h3>{t("onlineReport.summary")}</h3>
      <ReportTable
        rows={summary}
        columns={[
          { key: "period_type", label: t("onlineReport.columns.period_type") },
          { key: "period", label: t("onlineReport.columns.period") },
          {
            key: "trading_days",
            label: t("onlineReport.columns.trading_days"),
          },
          ...["net_annualized_return", "gross_sharpe", "net_max_drawdown"].map(
            (key) => ({
              key: `top${topN}_${key}`,
              label: t(`onlineReport.columns.${key}`),
              format:
                key === "gross_sharpe"
                  ? ("score" as const)
                  : ("percent" as const),
            }),
          ),
        ]}
      />
      <p className="online-caption">{t("onlineReport.labelsPending")}</p>
    </div>
  );
}
