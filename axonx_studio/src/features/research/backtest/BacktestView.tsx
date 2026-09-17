import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
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

function cumulativeRows(
  rows: DailyRow[],
  topNs: number[],
  benchmarks: BenchmarkDefinition[],
  compound: boolean,
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
      date: "起点",
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
  zh,
  remoteIp,
}: {
  meta: BacktestArtifact;
  zh: boolean;
  remoteIp?: string;
}) {
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
        <strong>
          {zh ? "无法读取新版回测产物" : "Unable to load backtest artifacts"}
        </strong>
        <span>
          {error || (zh ? "daily.parquet 为空" : "daily.parquet is empty")}
        </span>
      </div>
    );
  return <BacktestReport meta={meta} daily={daily} summary={summary} zh={zh} />;
}

function BacktestReport({
  meta,
  daily,
  summary,
  zh,
}: {
  meta: BacktestArtifact;
  daily: DailyRow[];
  summary: SummaryRow[];
  zh: boolean;
}) {
  const topNs = meta.dimensions?.top_ns || [1, 2, 3, 5, 10, 15, 20, 30];
  const benchmarks = meta.dimensions?.benchmarks || [
    { key: "universe", label: "全市场平均" },
  ];
  const [tab, setTab] = useState<
    "gross" | "net" | "quality" | "overall" | "year" | "quarter" | "month"
  >("gross");
  const [range, setRange] = useState<[number, number]>([0, daily.length - 1]);
  const [hoveredDate, setHoveredDate] = useState("");
  const [lockedDate, setLockedDate] = useState("");
  const tabs = [
    ["gross", zh ? "毛收益" : "Gross return"],
    ["net", zh ? "净收益" : "Net return"],
    ["quality", zh ? "模型质量" : "Model quality"],
    ["overall", zh ? "总体" : "Overall"],
    ["year", zh ? "分年" : "Yearly"],
    ["quarter", zh ? "分季度" : "Quarterly"],
    ["month", zh ? "分月" : "Monthly"],
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
          zh={zh}
        />
      ) : (
        <SummaryView
          rows={summary.filter((row) => row.period_type === tab)}
          topNs={topNs}
          benchmarks={benchmarks}
          zh={zh}
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
  zh,
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
  zh: boolean;
}) {
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
      if (date !== "起点") setHoveredDate(date);
    },
    [setHoveredDate],
  );
  const lock = useCallback(
    (date: string) => {
      if (date !== "起点")
        setLockedDate((current) => (current === date ? "" : date));
    },
    [setLockedDate],
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
    () => cumulativeRows(selected, topNs, benchmarks, false),
    [benchmarks, selected, topNs],
  );
  const netRows = useMemo(
    () => cumulativeRows(selected, topNs, benchmarks, true),
    [benchmarks, selected, topNs],
  );
  return (
    <div className="backtest-overview">
      <section className="range-toolbar">
        <label>
          <span>{zh ? "开始日期" : "From"}</span>
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
          labels={zh ? ["开始日期", "结束日期"] : ["Start date", "End date"]}
        />
        <label>
          <span>{zh ? "结束日期" : "To"}</span>
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
          {selected.length} {zh ? "个交易日" : "days"}
        </strong>
        <button
          onClick={() => setRange([0, daily.length - 1])}
          title={zh ? "恢复全部" : "Reset"}
        >
          <RotateCcw />
        </button>
      </section>
      {view === "gross" && (
        <ChartCard
          title={zh ? "毛收益累计" : "Cumulative gross return"}
          hint={
            zh
              ? "日收益算术累加，区间起点归零"
              : "Arithmetic sum rebased to zero"
          }
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
          title={zh ? "净收益复利" : "Compounded net return"}
          hint={
            zh
              ? "策略扣除换手手续费，基准不扣费"
              : "Strategies include turnover costs"
          }
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
          hint={zh ? "候选股票池内计算" : "Candidate universe"}
        >
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
          hint={
            zh ? "实际收益截面百分位 relevance" : "Return-percentile relevance"
          }
        >
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
          zh={zh}
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
  zh,
  onUnlock,
  onLatest,
}: {
  row?: DailyRow;
  locked: boolean;
  zh: boolean;
  onUnlock: () => void;
  onLatest: () => void;
}) {
  const holdings = (row?.top30_holdings || []) as Holding[];
  return (
    <section className="viz-card holdings-panel">
      <header>
        <div>
          <small>TOP 30 HOLDINGS</small>
          <h3>
            {row?.trade_date || "—"} · {holdings.length}{" "}
            {zh ? "只股票" : "stocks"}
          </h3>
        </div>
        <div className="holdings-actions">
          {locked && (
            <button type="button" onClick={onUnlock}>
              <LockKeyhole />
              {zh ? "取消锁定" : "Unlock"}
            </button>
          )}
          <button
            type="button"
            onClick={onLatest}
            title={
              zh
                ? "回到所选区间的最后一个交易日"
                : "Show the latest day in the selected range"
            }
          >
            <RotateCcw />
            {zh ? "回到最新" : "Latest"}
          </button>
        </div>
      </header>
      <div className="mini-table">
        <table>
          <thead>
            <tr>
              {[
                "#",
                zh ? "代码" : "Code",
                zh ? "名称" : "Name",
                zh ? "预测值" : "Prediction",
                zh ? "当日收益" : "Return",
                zh ? "权重" : "Weight",
              ].map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {holdings.map((item) => (
              <tr key={item.ts_code}>
                <td>{item.rank}</td>
                <td>
                  <code>{item.ts_code}</code>
                </td>
                <td>{item.name}</td>
                <td>{fixed(item.prediction, 6)}</td>
                <td
                  className={item.daily_return >= 0 ? "positive" : "negative"}
                >
                  {percent(item.daily_return)}
                </td>
                <td>{percent(item.weight)}</td>
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
  label: string;
  english: string;
  format: (value: unknown) => string;
  percent: boolean;
};

const performanceMetrics: SummaryMetric[] = [
  {
    key: "net_cumulative_return",
    label: "净累计收益",
    english: "Net cumulative return",
    format: percent,
    percent: true,
  },
  {
    key: "net_annualized_return",
    label: "净年化收益",
    english: "Net annualized return",
    format: percent,
    percent: true,
  },
  {
    key: "net_annualized_volatility",
    label: "年化波动率",
    english: "Annualized volatility",
    format: percent,
    percent: true,
  },
  {
    key: "net_max_drawdown",
    label: "最大回撤",
    english: "Max drawdown",
    format: percent,
    percent: true,
  },
  {
    key: "net_win_rate",
    label: "胜率",
    english: "Win rate",
    format: percent,
    percent: true,
  },
  {
    key: "average_turnover",
    label: "平均换手率",
    english: "Average turnover",
    format: percent,
    percent: true,
  },
  {
    key: "gross_cumulative_return",
    label: "毛累计收益",
    english: "Gross cumulative return",
    format: percent,
    percent: true,
  },
  {
    key: "gross_sharpe",
    label: "Sharpe",
    english: "Sharpe",
    format: fixed,
    percent: false,
  },
];

const signalMetrics: SummaryMetric[] = [
  {
    key: "trading_days",
    label: "交易日数",
    english: "Trading days",
    format: (value) => fixed(value, 0),
    percent: false,
  },
  {
    key: "ic_mean",
    label: "IC 均值",
    english: "IC mean",
    format: (value) => fixed(value, 4),
    percent: false,
  },
  {
    key: "icir",
    label: "ICIR",
    english: "ICIR",
    format: fixed,
    percent: false,
  },
  {
    key: "rank_ic_mean",
    label: "RankIC 均值",
    english: "RankIC mean",
    format: (value) => fixed(value, 4),
    percent: false,
  },
  {
    key: "rank_icir",
    label: "RankICIR",
    english: "RankICIR",
    format: fixed,
    percent: false,
  },
];

const metricName = (metric: SummaryMetric, zh: boolean) =>
  zh ? metric.label : metric.english;
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

function SummaryView({
  rows,
  topNs,
  benchmarks,
  zh,
}: {
  rows: SummaryRow[];
  topNs: number[];
  benchmarks: BenchmarkDefinition[];
  zh: boolean;
}) {
  const [topN, setTopN] = useState(topNs.includes(30) ? 30 : topNs[0]);
  const [leftKey, setLeftKey] = useState("net_cumulative_return");
  const [rightKey, setRightKey] = useState("net_max_drawdown");
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
  const selected = [leftKey, rightKey]
    .filter(Boolean)
    .map((key) => metrics.find((item) => item.key === key)!)
    .filter(Boolean);
  const periodName = (row: SummaryRow) =>
    overall ? `${row.period_start}—${row.period_end}` : row.period;
  const signalSeries: ChartSeries[] = [
    {
      key: "rank_ic_mean",
      label: "RankIC",
      type: "bar",
      axis: 0,
      format: "precise",
    },
    {
      key: "rank_icir",
      label: "RankICIR",
      type: "bar",
      axis: 1,
      format: "decimal",
    },
  ];
  const topSeries: ChartSeries[] = selected.map((metric, index) => ({
    key: metric.key,
    label: metricName(metric, zh),
    type: "bar",
    axis: index as 0 | 1,
    format: metric.percent ? "percent" : "decimal",
  }));
  const topChartRows: ChartRow[] = periods.map((row) => ({
    date: periodName(row),
    ...Object.fromEntries(
      selected.map(({ key }) => [key, metricValue(row, topN, key)]),
    ),
  }));
  if (!rows.length) return <div className="chart-empty">NO SUMMARY DATA</div>;
  const topNControl = (
    <label className="summary-select-label">
      <span>Top N</span>
      <select
        aria-label={zh ? "选择 Top N" : "Select Top N"}
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
            <small>{zh ? "与 Top N 无关" : "INDEPENDENT OF TOP N"}</small>
            <h3>{zh ? "整体指标" : "Overall metrics"}</h3>
          </div>
        </div>
        {overall && (
          <div className="summary-signal-cards">
            {signalMetrics.map(({ key, label, english, format }) => (
              <article key={key} className="viz-card">
                <span>{zh ? label : english}</span>
                <strong>{format(rows[0][key])}</strong>
              </article>
            ))}
          </div>
        )}
        {!overall && (
          <section className="viz-card period-chart summary-signal-chart">
            <header>
              <div>
                <small>SIGNAL QUALITY</small>
                <h3>RankIC · RankICIR</h3>
              </div>
              <span className="summary-axis-hint">
                {zh
                  ? "左轴：RankIC　右轴：RankICIR"
                  : "Left: RankIC · Right: RankICIR"}
              </span>
            </header>
            <BacktestChart
              rows={periods.map((row) => ({
                date: row.period,
                ...Object.fromEntries(
                  signalSeries.map(({ key }) => [key, row[key]]),
                ),
              }))}
              series={signalSeries}
              zoom
            />
          </section>
        )}
        <section className="viz-card summary-table summary-signal-table">
          <header>
            <div>
              <small>BASE METRICS</small>
              <h3>{zh ? "整体指标明细" : "Overall metric details"}</h3>
            </div>
          </header>
          <div
            className="mini-table"
            role="region"
            aria-label={zh ? "整体指标明细" : "Overall metric details"}
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>{zh ? "时间" : "Period"}</th>
                  {signalMetrics.map((metric) => (
                    <th key={metric.key}>{metricName(metric, zh)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {periods.map((row) => (
                  <tr key={row.period}>
                    <td>
                      <strong>{periodName(row)}</strong>
                    </td>
                    {signalMetrics.map(({ key, format }) => (
                      <td key={key}>{format(row[key])}</td>
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
            <small>{zh ? "按持仓数量筛选" : "FILTER BY PORTFOLIO SIZE"}</small>
            <h3>Top N {zh ? "指标" : "metrics"}</h3>
          </div>
        </div>
        {!overall && (
          <section className="viz-card period-chart summary-top-chart">
            <header>
              <div>
                <small>PERIOD PERFORMANCE</small>
                <h3>
                  {zh
                    ? `Top ${topN} · 收益与风险`
                    : `Top ${topN} · Return and risk`}
                </h3>
              </div>
              <div className="summary-chart-controls">
                {topNControl}
                <label className="summary-select-label">
                  <span>{zh ? "左轴" : "Left axis"}</span>
                  <select
                    aria-label={zh ? "选择左轴指标" : "Select left axis metric"}
                    value={leftKey}
                    onChange={(event) => setLeftKey(event.target.value)}
                  >
                    {metrics.map((metric) => (
                      <option
                        key={metric.key}
                        value={metric.key}
                        disabled={metric.key === rightKey}
                      >
                        {metricName(metric, zh)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="summary-select-label">
                  <span>{zh ? "右轴" : "Right axis"}</span>
                  <select
                    aria-label={
                      zh ? "选择右轴指标" : "Select right axis metric"
                    }
                    value={rightKey}
                    onChange={(event) => setRightKey(event.target.value)}
                  >
                    <option value="">{zh ? "不显示" : "None"}</option>
                    {metrics.map((metric) => (
                      <option
                        key={metric.key}
                        value={metric.key}
                        disabled={metric.key === leftKey}
                      >
                        {metricName(metric, zh)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </header>
            <BacktestChart rows={topChartRows} series={topSeries} zoom />
          </section>
        )}
        <section className="viz-card summary-table summary-detail-table">
          <header>
            <div>
              <small>TOP N DETAIL</small>
              <h3>
                {zh ? `Top ${topN} · 全部指标` : `Top ${topN} · All metrics`}
              </h3>
            </div>
            <div className="summary-chart-controls">
              {overall && topNControl}
              <span className="summary-table-hint">
                {zh ? "左右滑动查看" : "Scroll sideways"}
              </span>
            </div>
          </header>
          <div
            className="mini-table"
            role="region"
            aria-label={
              zh ? "Top N 分期指标明细" : "Top N period metric details"
            }
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>{zh ? "时间" : "Period"}</th>
                  {metrics.map((metric) => (
                    <th key={metric.key}>{metricName(metric, zh)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {periods.map((row) => (
                  <tr key={row.period}>
                    <td>
                      <strong>{periodName(row)}</strong>
                    </td>
                    {metrics.map(({ key, format }) => {
                      const value = metricValue(row, topN, key);
                      return (
                        <td key={key} className={valueTone(value)}>
                          {format(value)}
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
