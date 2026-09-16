import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
} from "lucide-react";
import { loadBacktest } from "./api";
import { BacktestChart } from "./BacktestChart";
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
  const [tab, setTab] = useState("overview");
  const tabs = [
    ["overview", zh ? "走势概览" : "Overview"],
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
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "overview" ? (
        <Overview daily={daily} topNs={topNs} benchmarks={benchmarks} zh={zh} />
      ) : tab === "overall" ? (
        <Overall
          rows={summary.filter((row) => row.period_type === "overall")}
          topNs={topNs}
          benchmarks={benchmarks}
          zh={zh}
        />
      ) : (
        <PeriodView
          period={tab as "year" | "quarter" | "month"}
          rows={summary.filter((row) => row.period_type === tab)}
          topNs={topNs}
          zh={zh}
        />
      )}
    </div>
  );
}

function Overview({
  daily,
  topNs,
  benchmarks,
  zh,
}: {
  daily: DailyRow[];
  topNs: number[];
  benchmarks: BenchmarkDefinition[];
  zh: boolean;
}) {
  const [range, setRange] = useState<[number, number]>([0, daily.length - 1]);
  const [hoveredDate, setHoveredDate] = useState(
    daily.at(-1)?.trade_date || "",
  );
  const [lockedDate, setLockedDate] = useState("");
  const updateRange = (position: 0 | 1, value: number) =>
    setRange(([start, end]) =>
      position === 0
        ? [Math.min(value, end), end]
        : [start, Math.max(value, start)],
    );
  const selected = useMemo(
    () => daily.slice(range[0], range[1] + 1),
    [daily, range],
  );
  const allSignals = useMemo(() => signalRows(daily), [daily]);
  const signals = useMemo(
    () => allSignals.slice(range[0], range[1] + 1),
    [allSignals, range],
  );
  const activeDate = lockedDate || hoveredDate || selected.at(-1)?.trade_date;
  const active =
    daily.find((row) => row.trade_date === activeDate) || selected.at(-1);
  const hover = useCallback((date: string) => {
    if (date !== "起点") setHoveredDate(date);
  }, []);
  const lock = useCallback((date: string) => {
    if (date !== "起点")
      setLockedDate((current) => (current === date ? "" : date));
  }, []);
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
        <div className="range-sliders">
          <input
            type="range"
            min="0"
            max={daily.length - 1}
            value={range[0]}
            onChange={(event) => updateRange(0, +event.target.value)}
          />
          <input
            type="range"
            min="0"
            max={daily.length - 1}
            value={range[1]}
            onChange={(event) => updateRange(1, +event.target.value)}
          />
        </div>
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
      <ChartCard
        title={zh ? "毛收益累计" : "Cumulative gross return"}
        hint={
          zh ? "日收益算术累加，区间起点归零" : "Arithmetic sum rebased to zero"
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
      <div className="backtest-half-grid">
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
      </div>
      <HoldingsPanel
        row={active}
        locked={Boolean(lockedDate)}
        zh={zh}
        onUnlock={() => setLockedDate("")}
      />
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
}: {
  row?: DailyRow;
  locked: boolean;
  zh: boolean;
  onUnlock: () => void;
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
        {locked && (
          <button onClick={onUnlock}>
            <LockKeyhole />
            {zh ? "取消锁定" : "Unlock"}
          </button>
        )}
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

function Overall({
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
  const row = rows[0];
  if (!row) return <div className="chart-empty">NO SUMMARY DATA</div>;
  return (
    <div className="summary-view">
      <div className="artifact-kpis">
        {[
          [zh ? "交易日" : "Days", fixed(row.trading_days, 0)],
          ["IC", fixed(row.ic_mean, 4)],
          ["ICIR", fixed(row.icir, 2)],
          [
            "RankIC / IR",
            `${fixed(row.rank_ic_mean, 4)} / ${fixed(row.rank_icir, 2)}`,
          ],
        ].map(([label, value]) => (
          <article key={label}>
            <small>{label}</small>
            <strong>{value}</strong>
            <span>
              {row.period_start}—{row.period_end}
            </span>
          </article>
        ))}
      </div>
      <section className="viz-card summary-table">
        <header>
          <div>
            <small>OVERALL PERFORMANCE</small>
            <h3>{zh ? "TopN 总体表现" : "TopN performance"}</h3>
          </div>
        </header>
        <div className="mini-table">
          <table>
            <thead>
              <tr>
                <th>Portfolio</th>
                {performanceColumns.map(([, label]) => (
                  <th key={label}>{label}</th>
                ))}
                {benchmarks.map((item) => (
                  <th key={item.key}>IR · {item.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topNs.map((topN) => (
                <tr key={topN}>
                  <td>
                    <strong>Top {topN}</strong>
                  </td>
                  {performanceColumns.map(([key, , format]) => (
                    <td key={key}>{format(row[`top${topN}_${key}`])}</td>
                  ))}
                  {benchmarks.map(({ key }) => (
                    <td key={key}>
                      {fixed(row[`top${topN}_information_ratio_${key}`])}
                    </td>
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

function PeriodView({
  period,
  rows,
  topNs,
  zh,
}: {
  period: "year" | "quarter" | "month";
  rows: SummaryRow[];
  topNs: number[];
  zh: boolean;
}) {
  const [topN, setTopN] = useState(topNs.includes(30) ? 30 : topNs[0]);
  const chartRows = rows.map((row) => ({
    date: row.period,
    net: row[`top${topN}_net_cumulative_return`],
    gross: row[`top${topN}_gross_cumulative_return`],
    drawdown: row[`top${topN}_net_max_drawdown`],
  }));
  return (
    <div className="summary-view">
      <section className="viz-card period-chart">
        <header>
          <div>
            <small>{period.toUpperCase()} PERFORMANCE</small>
            <h3>{zh ? "收益与回撤" : "Return and drawdown"}</h3>
          </div>
          <select
            value={topN}
            onChange={(event) => setTopN(+event.target.value)}
          >
            {topNs.map((value) => (
              <option key={value} value={value}>
                Top {value}
              </option>
            ))}
          </select>
        </header>
        <BacktestChart
          rows={chartRows}
          series={[
            { key: "net", label: zh ? "净收益" : "Net return", type: "bar" },
            {
              key: "gross",
              label: zh ? "毛收益" : "Gross return",
              type: "bar",
            },
            {
              key: "drawdown",
              label: zh ? "最大回撤" : "Max drawdown",
              axis: 1,
            },
          ]}
          percent
        />
      </section>
      <section className="viz-card summary-table">
        <header>
          <div>
            <small>PERIOD DETAILS</small>
            <h3>{zh ? "周期明细" : "Period details"}</h3>
          </div>
        </header>
        <div className="mini-table">
          <table>
            <thead>
              <tr>
                <th>{zh ? "时间" : "Period"}</th>
                <th>{zh ? "交易日" : "Days"}</th>
                <th>IC</th>
                <th>ICIR</th>
                {performanceColumns.map(([, label]) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.period}>
                  <td>
                    <strong>{row.period}</strong>
                  </td>
                  <td>{fixed(row.trading_days, 0)}</td>
                  <td>{fixed(row.ic_mean, 4)}</td>
                  <td>{fixed(row.icir)}</td>
                  {performanceColumns.map(([key, , format]) => (
                    <td key={key}>{format(row[`top${topN}_${key}`])}</td>
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
