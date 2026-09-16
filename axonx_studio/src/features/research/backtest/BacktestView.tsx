import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Columns3,
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

const number = (value: unknown) => Number(value);
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
  const [tab, setTab] = useState<"gross" | "net" | "quality" | "summary">(
    "gross",
  );
  const [range, setRange] = useState<[number, number]>([0, daily.length - 1]);
  const [hoveredDate, setHoveredDate] = useState("");
  const [lockedDate, setLockedDate] = useState("");
  const tabs = [
    ["gross", zh ? "毛收益" : "Gross return"],
    ["net", zh ? "净收益" : "Net return"],
    ["quality", zh ? "模型质量" : "Model quality"],
    ["summary", zh ? "汇总表" : "Summary"],
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
          rows={summary}
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

const performanceColumns = [
  ["net_cumulative_return", "净累计收益", percent],
  ["net_annualized_return", "净年化收益", percent],
  ["net_annualized_volatility", "年化波动率", percent],
  ["net_max_drawdown", "最大回撤", percent],
  ["net_win_rate", "胜率", percent],
  ["average_turnover", "平均换手率", percent],
  ["gross_cumulative_return", "毛累计收益", percent],
  ["gross_sharpe", "Sharpe", fixed],
] as const;

function ColumnPicker({
  columns,
  visible,
  onChange,
  zh,
}: {
  columns: { key: string; label: string }[];
  visible: string[];
  onChange: (keys: string[]) => void;
  zh: boolean;
}) {
  return (
    <details className="summary-column-picker">
      <summary>
        <Columns3 size={15} aria-hidden="true" />
        {zh ? "选择列" : "Columns"}
        <span>
          {visible.length}/{columns.length}
        </span>
      </summary>
      <div className="summary-column-menu">
        <div className="summary-column-menu-actions">
          <strong>{zh ? "显示指标" : "Visible metrics"}</strong>
          <button
            type="button"
            onClick={() => onChange(columns.map(({ key }) => key))}
          >
            {zh ? "显示全部" : "Show all"}
          </button>
        </div>
        {columns.map(({ key, label }) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={visible.includes(key)}
              disabled={visible.length === 1 && visible.includes(key)}
              onChange={() =>
                onChange(
                  visible.includes(key)
                    ? visible.filter((item) => item !== key)
                    : [...visible, key],
                )
              }
            />
            {label}
          </label>
        ))}
      </div>
    </details>
  );
}

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
  const baseColumns = [
    {
      key: "trading_days",
      label: zh ? "交易日数" : "Trading days",
      format: (value: unknown) => fixed(value, 0),
    },
    {
      key: "ic_mean",
      label: zh ? "IC均值" : "IC mean",
      format: (value: unknown) => fixed(value, 4),
    },
    { key: "icir", label: "ICIR", format: (value: unknown) => fixed(value) },
    {
      key: "rank_ic_mean",
      label: zh ? "RankIC均值" : "RankIC mean",
      format: (value: unknown) => fixed(value, 4),
    },
    {
      key: "rank_icir",
      label: "RankICIR",
      format: (value: unknown) => fixed(value),
    },
  ];
  const metricColumns = [
    ...baseColumns,
    ...topNs.flatMap((topN) => [
      ...performanceColumns.map(([key, label, format]) => ({
        key: "top" + topN + "_" + key,
        label: "Top " + topN + " · " + label,
        format,
      })),
      ...benchmarks.map(({ key, label }) => ({
        key: "top" + topN + "_information_ratio_" + key,
        label: "Top " + topN + " · IR · " + label,
        format: fixed,
      })),
    ]),
  ];
  const [visible, setVisible] = useState<string[]>(() =>
    metricColumns.map(({ key }) => key),
  );
  const visibleColumns = metricColumns.filter(({ key }) =>
    visible.includes(key),
  );
  const typeLabels = {
    overall: zh ? "总体" : "Overall",
    year: zh ? "分年" : "Yearly",
    quarter: zh ? "分季度" : "Quarterly",
    month: zh ? "分月" : "Monthly",
  };
  if (!rows.length) return <div className="chart-empty">NO SUMMARY DATA</div>;
  return (
    <div className="summary-view">
      <section className="viz-card summary-table combined-summary-table">
        <header>
          <div>
            <small>PERFORMANCE SUMMARY</small>
            <h3>{zh ? "回测指标汇总" : "Backtest performance summary"}</h3>
          </div>
          <div className="summary-table-actions">
            <span>
              {zh ? "左右滑动查看全部指标" : "Scroll sideways for more"}
            </span>
            <ColumnPicker
              columns={metricColumns}
              visible={visible}
              onChange={setVisible}
              zh={zh}
            />
          </div>
        </header>
        <div
          className="mini-table"
          role="region"
          aria-label={
            zh
              ? "回测指标汇总，可横向滚动"
              : "Backtest performance summary, horizontally scrollable"
          }
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>{zh ? "类型" : "Type"}</th>
                <th>{zh ? "时间" : "Period"}</th>
                {visibleColumns.map(({ key, label }) => (
                  <th key={key}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.period_type + ":" + row.period}>
                  <td>
                    <strong>{typeLabels[row.period_type]}</strong>
                  </td>
                  <td>
                    <strong>
                      {row.period_type === "overall"
                        ? row.period_start + "—" + row.period_end
                        : row.period}
                    </strong>
                  </td>
                  {visibleColumns.map(({ key, format }) => (
                    <td key={key}>{format(row[key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
