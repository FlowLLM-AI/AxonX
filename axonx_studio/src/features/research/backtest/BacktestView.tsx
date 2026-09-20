import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ListRestart,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
} from "lucide-react";
import { loadBacktest } from "./api";
import { BacktestChart } from "./BacktestChart";
import { DateRangeSlider } from "./DateRangeSlider";
import type {
  BacktestArtifact,
  BenchmarkDefinition,
  ChartRow,
  ChartSeries,
  DailyRow,
  Holding,
  SummaryRow,
} from "./types";

const number = (value: unknown) =>
  value == null || value === "" ? NaN : Number(value);
const fixed = (value: unknown, digits = 2) =>
  Number.isFinite(number(value)) ? number(value).toFixed(digits) : "—";
const percent = (value: unknown) =>
  Number.isFinite(number(value)) ? `${(number(value) * 100).toFixed(2)}%` : "—";
const inputDate = (value: string) =>
  `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
const compactDate = (value: string) => value.replaceAll("-", "");
const IC_SERIES: ChartSeries[] = [
  { key: "ic", label: "IC" },
  { key: "rank_ic", label: "RankIC" },
];
const NDCG_SERIES: ChartSeries[] = [5, 10, 15, 20, 30].map((topN) => ({
  key: `ndcg_${topN}`,
  label: `NDCG@${topN}`,
  sourceKey: `top${topN}_ndcg`,
}));
const lastOnOrBefore = (rows: DailyRow[], date: string) => {
  let index = 0;
  rows.forEach((row, current) => {
    if (row.trade_date <= date) index = current;
  });
  return index;
};

function movingAverage(rows: DailyRow[], key: string, window = 20) {
  return rows.map((_, index) => {
    const values = rows
      .slice(Math.max(0, index - window + 1), index + 1)
      .map((row) => number(row[key]))
      .filter(Number.isFinite);
    return values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : null;
  });
}

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

function cumulativeRows(
  rows: DailyRow[],
  topNs: number[],
  benchmarks: BenchmarkDefinition[],
  compound: boolean,
  startLabel: string,
): ChartRow[] {
  const totals = new Map<string, number>();
  const definitions = [
    ...topNs.map(
      (topN) =>
        [
          `top${topN}`,
          `top${topN}_${compound ? "net" : "gross"}_return`,
        ] as const,
    ),
    ...benchmarks.map(
      ({ key }) => [`benchmark_${key}`, `benchmark_${key}_return`] as const,
    ),
  ];
  for (const [key] of definitions) totals.set(key, compound ? 1 : 0);
  const result: ChartRow[] = [
    {
      date: startLabel,
      ...Object.fromEntries(definitions.map(([key]) => [key, 0])),
    },
  ];
  for (const row of rows) {
    const point: ChartRow = { date: row.trade_date };
    for (const [key, source] of definitions) {
      const daily = number(row[source]);
      if (!Number.isFinite(daily)) {
        point[key] = null;
        continue;
      }
      const next = compound
        ? (totals.get(key) || 1) * (1 + daily)
        : (totals.get(key) || 0) + daily;
      totals.set(key, next);
      point[key] = compound ? next - 1 : next;
    }
    result.push(point);
  }
  return result;
}

function signalRows(rows: DailyRow[]) {
  const ic = movingAverage(rows, "ic");
  const rankIc = movingAverage(rows, "rank_ic");
  const ndcg = [5, 10, 15, 20, 30].map(
    (topN) => [topN, movingAverage(rows, `top${topN}_ndcg`)] as const,
  );
  return rows.map((row, index) => ({
    date: row.trade_date,
    ic: ic[index],
    rank_ic: rankIc[index],
    ...Object.fromEntries(
      ndcg.map(([topN, values]) => [`ndcg_${topN}`, values[index]]),
    ),
  }));
}

export function BacktestView({
  meta,
  remoteIp,
}: {
  meta: BacktestArtifact;
  remoteIp?: string;
}) {
  const { t } = useTranslation();
  const [daily, setDaily] = useState<DailyRow[]>([]);
  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    loadBacktest(meta, remoteIp, controller.signal)
      .then((data) => {
        setDaily(data.daily);
        setSummary(data.summary);
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [meta, remoteIp]);

  if (loading)
    return (
      <div className="research-loading">
        <LoaderCircle className="spin" />
      </div>
    );
  if (error || !daily.length)
    return (
      <div className="data-gap">
        <AlertTriangle />
        <strong>{t("backtest.unable_to_load_backtest_artifacts")}</strong>
        <span>{error || t("backtest.daily_parquet_is_empty")}</span>
      </div>
    );
  return <BacktestReport meta={meta} daily={daily} summary={summary} />;
}

function BacktestReport({
  meta,
  daily,
  summary,
}: {
  meta: BacktestArtifact;
  daily: DailyRow[];
  summary: SummaryRow[];
}) {
  const { t } = useTranslation();
  const topNs = meta.dimensions?.top_ns || [1, 2, 3, 5, 10, 15, 20, 30];
  const benchmarks = meta.dimensions?.benchmarks || [
    { key: "universe", label: t("backtest.marketAverage") },
  ];
  const [tab, setTab] = useState<
    "gross" | "net" | "quality" | "overall" | "year" | "quarter" | "month"
  >("gross");
  const [range, setRange] = useState<[number, number]>([0, daily.length - 1]);
  const [hoveredDate, setHoveredDate] = useState("");
  const [lockedDate, setLockedDate] = useState("");
  const tabs = [
    ["gross", t("backtest.gross_return")],
    ["net", t("backtest.net_return")],
    ["quality", t("backtest.model_quality")],
    ["overall", t("backtest.overall")],
    ["year", t("backtest.yearly")],
    ["quarter", t("backtest.quarterly")],
    ["month", t("backtest.monthly")],
  ];
  return (
    <div className="backtest-report">
      <nav className="backtest-tabs">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            onClick={() => setTab(key as typeof tab)}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "gross" || tab === "net" || tab === "quality" ? (
        <Overview
          view={tab}
          daily={daily}
          topNs={topNs}
          benchmarks={benchmarks}
          range={range}
          setRange={setRange}
          hoveredDate={hoveredDate}
          setHoveredDate={setHoveredDate}
          lockedDate={lockedDate}
          setLockedDate={setLockedDate}
        />
      ) : (
        <SummaryView
          rows={summary.filter((row) => row.period_type === tab)}
          topNs={topNs}
          benchmarks={benchmarks}
        />
      )}
    </div>
  );
}

function Overview({
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
  const allSignals = useMemo(() => signalRows(daily), [daily]);
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
          <SeriesMeans rows={selected} series={NDCG_SERIES} />
          <BacktestChart
            rows={signals}
            series={NDCG_SERIES}
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

function HoldingsPanel({
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
                <td
                  className={item.daily_return >= 0 ? "positive" : "negative"}
                >
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

type SummaryMetric = {
  key: string;
  format: (value: unknown) => string;
  percent: boolean;
};

const performanceMetrics: SummaryMetric[] = [
  {
    key: "net_cumulative_return",
    format: percent,
    percent: true,
  },
  {
    key: "net_annualized_return",
    format: percent,
    percent: true,
  },
  {
    key: "net_annualized_volatility",
    format: percent,
    percent: true,
  },
  {
    key: "net_max_drawdown",
    format: percent,
    percent: true,
  },
  {
    key: "net_win_rate",
    format: percent,
    percent: true,
  },
  {
    key: "average_turnover",
    format: percent,
    percent: true,
  },
  {
    key: "gross_cumulative_return",
    format: percent,
    percent: true,
  },
  {
    key: "gross_sharpe",
    format: fixed,
    percent: false,
  },
];

const signalMetrics: SummaryMetric[] = [
  {
    key: "trading_days",
    format: (value) => fixed(value, 0),
    percent: false,
  },
  {
    key: "ic_mean",
    format: (value) => fixed(value, 4),
    percent: false,
  },
  {
    key: "icir",
    format: fixed,
    percent: false,
  },
  {
    key: "rank_ic_mean",
    format: (value) => fixed(value, 4),
    percent: false,
  },
  {
    key: "rank_icir",
    format: fixed,
    percent: false,
  },
];

const metricValue = (row: SummaryRow, topN: number, key: string) =>
  row[`top${topN}_${key}`];
const valueTone = (value: unknown) =>
  value == null || !Number.isFinite(Number(value))
    ? ""
    : Number(value) < 0
      ? "negative"
      : Number(value) > 0
        ? "positive"
        : "";
type SummarySort = { key: string; direction: "asc" | "desc" } | null;
const nextSummarySort = (current: SummarySort, key: string): SummarySort => ({
  key,
  direction:
    current?.key === key && current.direction === "asc" ? "desc" : "asc",
});
const dataBarDomain = (values: unknown[]) => {
  const finite = values.map(number).filter(Number.isFinite);
  return {
    min: Math.min(0, ...finite),
    max: Math.max(0, ...finite),
  };
};

function SummaryDataCell({
  value,
  format,
  domain,
}: {
  value: unknown;
  format: (value: unknown) => string;
  domain?: { min: number; max: number };
}) {
  const numeric = number(value);
  const zero = domain
    ? (-domain.min / (domain.max - domain.min || 1)) * 100
    : 0;
  const position = Number.isFinite(numeric)
    ? domain && numeric < 0
      ? zero + (numeric / (domain.max - domain.min || 1)) * 100
      : zero
    : 0;
  const width = Number.isFinite(numeric)
    ? Math.abs(numeric / ((domain?.max ?? 0) - (domain?.min ?? 0) || 1)) * 100
    : 0;
  return (
    <span className="summary-data-cell">
      {domain && domain.min < 0 && domain.max > 0 && (
        <span
          className="summary-data-zero"
          style={{ left: `${zero}%` }}
          aria-hidden="true"
        />
      )}
      {domain && width > 0 && (
        <span
          className={`summary-data-bar${numeric < 0 ? " negative" : ""}`}
          style={{ left: `${position}%`, width: `${width}%` }}
          aria-hidden="true"
        />
      )}
      <span className="summary-data-value">{format(value)}</span>
    </span>
  );
}

function SummaryView({
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
    ...benchmarks.map(({ key, label }) => ({
      key: `information_ratio_${key}`,
      label: `IR · ${label}`,
      english: `IR · ${label}`,
      format: fixed,
      percent: false,
    })),
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
      <select
        aria-label={t("backtest.select_top_n")}
        value={topN}
        onChange={(event) => setTopN(Number(event.target.value))}
      >
        {topNs.map((n) => (
          <option key={n} value={n}>
            Top {n}
          </option>
        ))}
      </select>
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
                      t(`backtest.metrics.${metric.key}`),
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
