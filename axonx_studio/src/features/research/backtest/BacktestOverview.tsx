import { RotateCcw } from "lucide-react";
import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  compactDate,
  formatFixed as fixed,
  dateInput as inputDate,
  toNumber as number,
} from "../../../shared/lib/format";
import { BacktestChart } from "./BacktestChart";
import { DateRangeSlider } from "./DateRangeSlider";
import { HoldingsPanel } from "./HoldingsTable";
import { cumulativeRows, IC_SERIES, lastOnOrBefore, signalRows } from "./model";
import type { BenchmarkDefinition, ChartSeries, DailyRow } from "./types";

function SeriesMeans({
  rows,
  series,
}: {
  rows: DailyRow[];
  series: ChartSeries[];
}) {
  const { t } = useTranslation();
  return (
    <div className="backtest-series-means">
      <small>{t("backtest.daily_mean_in_range")}</small>
      {series.map(({ key, label, sourceKey }) => {
        const values = rows
          .map((row) => number(row[sourceKey || key]))
          .filter(Number.isFinite);
        const mean = values.length
          ? values.reduce((sum, value) => sum + value, 0) / values.length
          : NaN;
        return (
          <span key={key}>
            <em>{label}</em>
            <strong>{fixed(mean, 4)}</strong>
          </span>
        );
      })}
    </div>
  );
}

export function Overview({
  view,
  daily,
  topNs,
  benchmarks,
  range,
  setRange,
  hoveredDate,
  setHoveredDate,
  lockedDate,
  setLockedDate,
}: {
  view: "gross" | "net" | "quality";
  daily: DailyRow[];
  topNs: number[];
  benchmarks: BenchmarkDefinition[];
  range: [number, number];
  setRange: React.Dispatch<React.SetStateAction<[number, number]>>;
  hoveredDate: string;
  setHoveredDate: React.Dispatch<React.SetStateAction<string>>;
  lockedDate: string;
  setLockedDate: React.Dispatch<React.SetStateAction<string>>;
}) {
  const { t } = useTranslation();
  const updateRange = (position: 0 | 1, value: number) =>
    setRange((current) => {
      const [start, end] = current;
      const next: [number, number] =
        position === 0
          ? [Math.min(value, end), end]
          : [start, Math.max(value, start)];
      return next[0] === start && next[1] === end ? current : next;
    });
  const selected = useMemo(
    () => daily.slice(range[0], range[1] + 1),
    [daily, range],
  );
  const allSignals = useMemo(() => signalRows(daily, topNs), [daily, topNs]);
  const ndcgSeries: ChartSeries[] = topNs.map((topN) => ({
    key: `ndcg_${topN}`,
    label: `NDCG@${topN}`,
    sourceKey: `top${topN}_ndcg`,
  }));
  const signals = useMemo(
    () => allSignals.slice(range[0], range[1] + 1),
    [allSignals, range],
  );
  const selectedDates = new Set(selected.map((row) => row.trade_date));
  const activeDate =
    (selectedDates.has(lockedDate) && lockedDate) ||
    (selectedDates.has(hoveredDate) && hoveredDate) ||
    selected.at(-1)?.trade_date;
  const active =
    daily.find((row) => row.trade_date === activeDate) || selected.at(-1);
  const hover = useCallback(
    (date: string) => {
      if (date !== t("common.start")) setHoveredDate(date);
    },
    [setHoveredDate, t],
  );
  const lock = useCallback(
    (date: string) => {
      if (date !== t("common.start"))
        setLockedDate((current) => (current === date ? "" : date));
    },
    [setLockedDate, t],
  );
  const returnSeries = useMemo<ChartSeries[]>(
    () => [
      ...topNs.map((topN) => ({ key: `top${topN}`, label: `Top ${topN}` })),
      ...benchmarks.map(({ key, label }) => ({
        key: `benchmark_${key}`,
        label,
        dashed: true,
      })),
    ],
    [benchmarks, topNs],
  );
  const grossRows = useMemo(
    () => cumulativeRows(selected, topNs, benchmarks, false, t("common.start")),
    [benchmarks, selected, topNs, t],
  );
  const netRows = useMemo(
    () => cumulativeRows(selected, topNs, benchmarks, true, t("common.start")),
    [benchmarks, selected, topNs, t],
  );
  return (
    <div className="backtest-overview">
      <section className="range-toolbar">
        <label>
          <span>{t("backtest.from")}</span>
          <input
            type="date"
            value={inputDate(daily[range[0]].trade_date)}
            min={inputDate(daily[0].trade_date)}
            max={inputDate(daily[range[1]].trade_date)}
            onChange={(event) => {
              const target = compactDate(event.target.value);
              updateRange(
                0,
                Math.max(
                  0,
                  daily.findIndex((row) => row.trade_date >= target),
                ),
              );
            }}
          />
        </label>
        <DateRangeSlider
          range={range}
          count={daily.length}
          onChange={updateRange}
          labels={[t("backtest.dateRange.start"), t("backtest.dateRange.end")]}
        />
        <label>
          <span>{t("backtest.to")}</span>
          <input
            type="date"
            value={inputDate(daily[range[1]].trade_date)}
            min={inputDate(daily[range[0]].trade_date)}
            max={inputDate(daily.at(-1)!.trade_date)}
            onChange={(event) => {
              const target = compactDate(event.target.value);
              updateRange(1, lastOnOrBefore(daily, target));
            }}
          />
        </label>
        <strong>
          {selected.length} {t("backtest.days")}
        </strong>
        <button
          onClick={() => setRange([0, daily.length - 1])}
          title={t("backtest.reset")}
        >
          <RotateCcw />
        </button>
      </section>
      {view === "gross" && (
        <ChartCard
          title={t("backtest.cumulative_gross_return")}
          hint={t("backtest.arithmetic_sum_rebased_to_zero")}
        >
          <BacktestChart
            rows={grossRows}
            series={returnSeries}
            percent
            onHover={hover}
            onSelect={lock}
          />
        </ChartCard>
      )}
      {view === "net" && (
        <ChartCard
          title={t("backtest.compounded_net_return")}
          hint={t("backtest.strategies_include_turnover_costs")}
        >
          <BacktestChart
            rows={netRows}
            series={returnSeries}
            percent
            onHover={hover}
            onSelect={lock}
          />
        </ChartCard>
      )}
      {view === "quality" && (
        <ChartCard
          title="IC / RankIC · MA20"
          hint={t("backtest.candidate_universe")}
        >
          <SeriesMeans rows={selected} series={IC_SERIES} />
          <BacktestChart
            rows={signals}
            series={IC_SERIES}
            onHover={hover}
            onSelect={lock}
          />
        </ChartCard>
      )}
      {view === "quality" && (
        <ChartCard
          title="NDCG · MA20"
          hint={t("backtest.return_percentile_relevance")}
        >
          <SeriesMeans rows={selected} series={ndcgSeries} />
          <BacktestChart
            rows={signals}
            series={ndcgSeries}
            onHover={hover}
            onSelect={lock}
          />
        </ChartCard>
      )}
      {(view === "gross" || view === "net") && (
        <HoldingsPanel
          row={active}
          locked={Boolean(lockedDate && selectedDates.has(lockedDate))}
          onUnlock={() => setLockedDate("")}
          onLatest={() => {
            setLockedDate("");
            setHoveredDate("");
          }}
        />
      )}
    </div>
  );
}

function ChartCard({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <section className="viz-card backtest-chart-card">
      <header>
        <div>
          <small>BACKTEST SERIES</small>
          <h3>{title}</h3>
        </div>
        <span>{hint}</span>
      </header>
      {children}
    </section>
  );
}
