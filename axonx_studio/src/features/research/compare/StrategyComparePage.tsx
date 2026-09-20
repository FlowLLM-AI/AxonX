import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeftRight,
  CalendarDays,
  GitCompareArrows,
  LoaderCircle,
  RefreshCw,
  Search,
} from "lucide-react";
import type { Language } from "../../../app/types";
import { listTaskRuns, previewWorkspaceFile } from "../../workspace/api";
import { BacktestChart } from "../backtest/BacktestChart";
import { loadBacktestDaily } from "../backtest/api";
import type {
  BacktestArtifact,
  ChartRow,
  ChartSeries,
  DailyRow,
  Holding,
} from "../backtest/types";
import {
  cumulativeSeries,
  finite,
  holdingOverlap,
  pairDays,
  pairedMean,
  pairedRatio,
  periodComparison,
  rollingQuality,
  strategyStats,
  type PairedDay,
  type PeriodUnit,
} from "./model";

type CompareTab = "overview" | "returns" | "periods" | "quality" | "trading";
type CompareTask = BacktestArtifact & {
  settings: {
    transactionCost?: number;
    annualizationDays?: number;
    riskFreeRate?: number;
  };
};

const numeric = (value: unknown) => {
  const number = finite(value);
  return Number.isFinite(number) ? number : NaN;
};
const percent = (value: number) =>
  Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "—";
const decimal = (value: number, digits = 3) =>
  Number.isFinite(value) ? value.toFixed(digits) : "—";
const dateInput = (value: string) =>
  `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
const compactDate = (value: string) => value.replaceAll("-", "");

async function loadTasks(
  remoteIp: string | undefined,
  signal: AbortSignal,
): Promise<CompareTask[]> {
  const directory = await listTaskRuns("backtest", remoteIp, signal);
  const records = await Promise.all(
    directory.entries
      .filter((entry) => entry.kind === "directory")
      .map(async (entry): Promise<CompareTask | null> => {
        try {
          const preview = await previewWorkspaceFile(
            `${entry.path}/metadata.json`,
            0,
            200,
            remoteIp,
            signal,
          );
          if (
            preview.kind !== "json" ||
            !preview.data ||
            typeof preview.data !== "object" ||
            Array.isArray(preview.data)
          )
            return null;
          const raw = preview.data as Record<string, unknown>;
          const input = (raw.input_params || {}) as Record<string, unknown>;
          const output = (raw.output_params || {}) as Record<string, unknown>;
          const artifacts = output.artifacts as
            BacktestArtifact["artifacts"] | undefined;
          if (!artifacts?.daily?.path) return null;
          return {
            _path: entry.path,
            task_key: String(raw.reg_name || "backtest"),
            created_at: String(raw.created_at || ""),
            config: {
              task_id: String(raw.task_id || entry.name),
              task_type: "backtest" as const,
              task_name: String(input.task_name || "backtest"),
              include_time: Boolean(input.include_time),
            },
            artifacts,
            dimensions: output.dimensions as BacktestArtifact["dimensions"],
            date_range: output.date_range as BacktestArtifact["date_range"],
            days: numeric(output.days),
            source: Array.isArray(input.source_tasks)
              ? input.source_tasks.filter(
                  (value): value is string => typeof value === "string",
                )
              : [],
            settings: {
              transactionCost: numeric(input.transaction_cost_rate),
              annualizationDays: numeric(input.annualization_days),
              riskFreeRate: numeric(input.annual_risk_free_rate),
            },
          } satisfies CompareTask;
        } catch {
          return null;
        }
      }),
  );
  return records
    .filter((task): task is CompareTask => task !== null)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function ComparisonTable({
  rows,
  zh,
}: {
  rows: {
    label: string;
    a: number;
    b: number;
    format: (value: number) => string;
  }[];
  zh: boolean;
}) {
  return (
    <div className="compare-table-wrap">
      <table className="compare-table">
        <thead>
          <tr>
            <th>{zh ? "指标" : "Metric"}</th>
            <th>A</th>
            <th>B</th>
            <th>{zh ? "差值 B − A" : "Difference B − A"}</th>
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
  zh,
  percentAxis = true,
}: {
  title: string;
  rows: ChartRow[];
  series: ChartSeries[];
  zh: boolean;
  percentAxis?: boolean;
}) {
  return (
    <section className="viz-card compare-chart-card">
      <header>
        <div>
          <small>{zh ? "共同区间" : "COMMON WINDOW"}</small>
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
    equityA *= 1 + numeric(point.a[`top${topN}_net_return`]);
    equityB *= 1 + numeric(point.b[`top${topN}_net_return`]);
    peakA = Math.max(peakA, equityA);
    peakB = Math.max(peakB, equityB);
    return { date: point.date, a: equityA / peakA - 1, b: equityB / peakB - 1 };
  });
}

export function StrategyComparePage({
  language,
  remoteIp,
  initialTaskId,
  onConnection,
}: {
  language: Language;
  remoteIp?: string;
  initialTaskId?: string;
  onConnection: (online: boolean) => void;
}) {
  const zh = language === "zh";
  const [tasks, setTasks] = useState<CompareTask[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState("");
  const [idA, setIdA] = useState(initialTaskId || "");
  const [idB, setIdB] = useState("");
  const [dailyA, setDailyA] = useState<DailyRow[]>([]);
  const [dailyB, setDailyB] = useState<DailyRow[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState("");
  const [loadedPair, setLoadedPair] = useState("");
  const [topN, setTopN] = useState(30);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [tab, setTab] = useState<CompareTab>("overview");
  const [returnMode, setReturnMode] = useState<"net" | "gross">("net");
  const [periodUnit, setPeriodUnit] = useState<PeriodUnit>("year");
  const [qualityKey, setQualityKey] = useState("rank_ic");
  const [holdingDate, setHoldingDate] = useState("");
  const toggleTask = (taskId: string) => {
    if (idA === taskId) setIdA("");
    else if (idB === taskId) setIdB("");
    else if (!idA) setIdA(taskId);
    else setIdB(taskId);
    setFrom("");
    setTo("");
    setHoldingDate("");
  };

  useEffect(() => {
    if (initialTaskId) setIdA(initialTaskId);
  }, [initialTaskId]);
  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true);
    setListError("");
    loadTasks(remoteIp, controller.signal)
      .then((values) => {
        if (!controller.signal.aborted) {
          setTasks(values);
          onConnection(true);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setListError(String(error));
          onConnection(false);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setListLoading(false);
      });
    return () => controller.abort();
  }, [remoteIp, reload, onConnection]);

  const taskA = tasks.find((task) => task.config.task_id === idA);
  const taskB = tasks.find((task) => task.config.task_id === idB);
  useEffect(() => {
    if (!taskA || !taskB || idA === idB) {
      setDailyA([]);
      setDailyB([]);
      setLoadedPair("");
      return;
    }
    const controller = new AbortController();
    setDataLoading(true);
    setDataError("");
    Promise.all([
      loadBacktestDaily(taskA, remoteIp, controller.signal),
      loadBacktestDaily(taskB, remoteIp, controller.signal),
    ])
      .then(([a, b]) => {
        setDailyA(a);
        setDailyB(b);
        setLoadedPair(`${idA}\n${idB}`);
        onConnection(true);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setDataError(String(error));
          onConnection(false);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setDataLoading(false);
      });
    return () => controller.abort();
  }, [taskA, taskB, idA, idB, remoteIp, onConnection]);

  const commonTopNs =
    taskA && taskB
      ? (taskA.dimensions?.top_ns || [1, 2, 3, 5, 10, 15, 20, 30]).filter((n) =>
          (taskB.dimensions?.top_ns || [1, 2, 3, 5, 10, 15, 20, 30]).includes(
            n,
          ),
        )
      : [];
  const selectedTopN = commonTopNs.includes(topN)
    ? topN
    : commonTopNs.at(-1) || 30;
  const points = useMemo(
    () => pairDays(dailyA, dailyB, selectedTopN),
    [dailyA, dailyB, selectedTopN],
  );
  const visible = useMemo(
    () =>
      points.filter(
        (point) =>
          (!from || point.date >= compactDate(from)) &&
          (!to || point.date <= compactDate(to)),
      ),
    [points, from, to],
  );
  const annualizationDays =
    taskA &&
    taskB &&
    Number.isFinite(taskA.settings.annualizationDays) &&
    taskA.settings.annualizationDays === taskB.settings.annualizationDays
      ? taskA.settings.annualizationDays!
      : 252;
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
  const availableTasks = tasks.filter((task) =>
    `${task.config.task_id} ${task.config.task_name}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const tabs: [CompareTab, string, string][] = [
    ["overview", "概览", "Overview"],
    ["returns", "收益与风险", "Return & risk"],
    ["periods", "分期表现", "Periods"],
    ["quality", "信号质量", "Signal quality"],
    ["trading", "交易与持仓", "Trading & holdings"],
  ];
  const warnings: string[] = [];
  if (taskA && taskB) {
    if (
      Number.isFinite(taskA.settings.transactionCost) &&
      Number.isFinite(taskB.settings.transactionCost) &&
      taskA.settings.transactionCost !== taskB.settings.transactionCost
    )
      warnings.push(zh ? "手续费参数不同" : "Transaction costs differ");
    if (
      Number.isFinite(taskA.settings.annualizationDays) &&
      Number.isFinite(taskB.settings.annualizationDays) &&
      taskA.settings.annualizationDays !== taskB.settings.annualizationDays
    )
      warnings.push(
        zh
          ? "原任务年化天数不同；对比统一按 252 天计算"
          : "Annualization differs; comparison uses 252 days",
      );
    if ((taskA.source || []).join() !== (taskB.source || []).join())
      warnings.push(zh ? "上游预测任务不同" : "Prediction sources differ");
    if (dailyA.length !== points.length || dailyB.length !== points.length)
      warnings.push(
        zh
          ? "比较仅使用共同且收益有效的交易日"
          : "Only shared days with valid returns are compared",
      );
  }
  const metricRows = [
    {
      label: zh ? "净累计收益" : "Net cumulative return",
      a: statsA.cumulative,
      b: statsB.cumulative,
      format: percent,
    },
    {
      label: zh ? "净年化收益" : "Net annualized return",
      a: statsA.annualized,
      b: statsB.annualized,
      format: percent,
    },
    {
      label: zh ? "年化波动率" : "Annualized volatility",
      a: statsA.volatility,
      b: statsB.volatility,
      format: percent,
    },
    {
      label: zh ? "最大回撤" : "Max drawdown",
      a: statsA.maxDrawdown,
      b: statsB.maxDrawdown,
      format: percent,
    },
    {
      label: zh ? "胜率" : "Win rate",
      a: statsA.winRate,
      b: statsB.winRate,
      format: percent,
    },
    {
      label: zh ? "平均换手率" : "Average turnover",
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
    <section className="workspace-page strategy-compare-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">RESEARCH / COMPARE</p>
          <h1>{zh ? "策略对比" : "Strategy comparison"}</h1>
          <span>
            {zh
              ? "在相同交易日和持仓数量下，观察两份回测的差异"
              : "Compare backtests on shared trading days and portfolio size"}
          </span>
        </div>
      </div>
      <div className="compare-layout">
        <aside className="compare-picker rail-panel run-index">
          <header className="run-index-header rail-header">
            <div className="run-index-heading rail-heading">
              <small>TASK VERSIONS</small>
              <strong>{zh ? "任务版本" : "Task versions"}</strong>
            </div>
            <div className="run-index-tools">
              <em>{tasks.length}</em>
              <button
                type="button"
                className="run-index-refresh rail-refresh"
                onClick={() => setReload((value) => value + 1)}
                aria-label={zh ? "刷新任务" : "Refresh tasks"}
              >
                <RefreshCw className={listLoading ? "spin" : ""} />
              </button>
            </div>
          </header>
          <label className="run-index-search rail-search">
            <Search />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={zh ? "搜索 task_id" : "Search task_id"}
            />
          </label>
          <div className="compare-picker-list rail-scroll">
            <p className="compare-picker-hint">
              {zh
                ? "点击两个版本进行对比；再次点击可取消"
                : "Click two versions to compare; click again to remove"}
            </p>
            {listLoading && (
              <p className="compare-state">
                <LoaderCircle className="spin" />
                {zh ? "正在读取任务" : "Loading tasks"}
              </p>
            )}
            {listError && (
              <p className="compare-state error">
                <AlertTriangle />
                {listError}
              </p>
            )}
            {!listLoading && !listError && !tasks.length && (
              <p className="compare-state">
                {zh ? "暂无可用回测任务" : "No backtests available"}
              </p>
            )}
            {availableTasks.map((task) => (
              <article
                className={
                  idA === task.config.task_id || idB === task.config.task_id
                    ? "active"
                    : ""
                }
                key={task.config.task_id}
              >
                <button
                  className="run-main rail-list-item compare-run-item"
                  type="button"
                  aria-pressed={
                    idA === task.config.task_id || idB === task.config.task_id
                  }
                  onClick={() => toggleTask(task.config.task_id)}
                >
                  <span className="run-item-avatar rail-avatar run-kind-backtest">
                    {task.task_key.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="rail-item-copy">
                    <strong>{task.task_key}</strong>
                    <code title={task.config.task_id}>
                      {task.config.task_id}
                    </code>
                    <small>
                      {task.created_at
                        ? new Date(task.created_at).toLocaleString(
                            zh ? "zh-CN" : "en",
                          )
                        : zh
                          ? "元数据不可用"
                          : "Metadata unavailable"}
                    </small>
                  </span>
                  <span
                    className={`compare-slot-badge${idA === task.config.task_id ? " slot-a" : idB === task.config.task_id ? " slot-b" : ""}`}
                  >
                    {idA === task.config.task_id
                      ? "A"
                      : idB === task.config.task_id
                        ? "B"
                        : "+"}
                  </span>
                </button>
              </article>
            ))}
          </div>
        </aside>
        <main className="compare-main">
          <div className="compare-selection">
            {([taskA, taskB] as const).map((task, index) => (
              <div
                className={`compare-selected compare-side-${index === 0 ? "a" : "b"}`}
                key={index}
              >
                <span>{index === 0 ? "A" : "B"}</span>
                <div>
                  <small>{zh ? "回测任务" : "Backtest task"}</small>
                  <strong title={task?.config.task_id}>
                    {task?.config.task_id ||
                      (zh ? "从左侧选择" : "Choose from the list")}
                  </strong>
                </div>
              </div>
            ))}
            <button
              type="button"
              className="compare-swap"
              disabled={!idA || !idB}
              onClick={() => {
                setIdA(idB);
                setIdB(idA);
              }}
              aria-label={zh ? "交换 A 和 B" : "Swap A and B"}
            >
              <ArrowLeftRight />
            </button>
          </div>
          {!taskA || !taskB ? (
            <div className="compare-empty">
              <GitCompareArrows />
              <strong>
                {zh
                  ? "选择两份回测任务开始对比"
                  : "Select two backtests to compare"}
              </strong>
              <span>
                {tasks.length === 1
                  ? zh
                    ? "目前只有一份回测任务；需要再运行一份回测才能比较"
                    : "Only one backtest is available; run another to compare"
                  : zh
                    ? "点击左侧两个任务版本，分别设为 A 和 B"
                    : "Click two task versions on the left to assign A and B"}
              </span>
            </div>
          ) : dataError ? (
            <div className="compare-empty error">
              <AlertTriangle />
              <strong>
                {zh ? "无法读取回测数据" : "Unable to load backtests"}
              </strong>
              <span>{dataError}</span>
            </div>
          ) : dataLoading || loadedPair !== `${idA}\n${idB}` ? (
            <div className="compare-empty">
              <LoaderCircle className="spin" />
              <strong>
                {zh ? "正在计算共同区间" : "Calculating shared window"}
              </strong>
            </div>
          ) : !commonTopNs.length ? (
            <div className="compare-empty error">
              <AlertTriangle />
              <strong>{zh ? "没有共同的 Top N" : "No shared Top N"}</strong>
            </div>
          ) : !points.length ? (
            <div className="compare-empty error">
              <CalendarDays />
              <strong>
                {zh ? "没有共同且有效的交易日" : "No shared valid trading days"}
              </strong>
            </div>
          ) : (
            <>
              <div className="compare-controls">
                <div className="compare-window">
                  <CalendarDays />
                  <div>
                    <small>{zh ? "共同区间" : "Shared window"}</small>
                    <strong>
                      {points[0].date} — {points.at(-1)?.date} · {points.length}{" "}
                      {zh ? "日" : "days"}
                    </strong>
                  </div>
                </div>
                <label>
                  Top N
                  <select
                    value={selectedTopN}
                    onChange={(event) => setTopN(Number(event.target.value))}
                  >
                    {commonTopNs.map((n) => (
                      <option value={n} key={n}>
                        Top {n}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {zh ? "开始" : "From"}
                  <input
                    type="date"
                    min={dateInput(points[0].date)}
                    max={dateInput(points.at(-1)!.date)}
                    value={from}
                    onChange={(event) => setFrom(event.target.value)}
                  />
                </label>
                <label>
                  {zh ? "结束" : "To"}
                  <input
                    type="date"
                    min={dateInput(points[0].date)}
                    max={dateInput(points.at(-1)!.date)}
                    value={to}
                    onChange={(event) => setTo(event.target.value)}
                  />
                </label>
                {(from || to) && (
                  <button
                    type="button"
                    onClick={() => {
                      setFrom("");
                      setTo("");
                    }}
                  >
                    {zh ? "重置日期" : "Reset dates"}
                  </button>
                )}
              </div>
              {warnings.length > 0 && (
                <div className="compare-warnings">
                  <AlertTriangle />
                  {warnings.map((warning) => (
                    <span key={warning}>{warning}</span>
                  ))}
                </div>
              )}
              {!visible.length ? (
                <div className="compare-empty">
                  <CalendarDays />
                  <strong>
                    {zh
                      ? "所选日期范围没有共同交易日"
                      : "No shared days in this date range"}
                  </strong>
                </div>
              ) : (
                <>
                  <nav
                    className="compare-tabs"
                    aria-label={zh ? "对比维度" : "Comparison dimensions"}
                  >
                    {tabs.map(([key, cn, en]) => (
                      <button
                        key={key}
                        type="button"
                        className={tab === key ? "active" : ""}
                        onClick={() => setTab(key)}
                      >
                        {zh ? cn : en}
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
                              {zh ? "差值" : "Difference"}{" "}
                              {metric.format(metric.b - metric.a)}
                            </em>
                          </article>
                        ))}
                      </div>
                      <ComparisonChart
                        title={
                          zh
                            ? "净收益累计 · 同起点"
                            : "Cumulative net return · shared start"
                        }
                        rows={cumulativeSeries(visible, selectedTopN)}
                        series={chartSeries}
                        zh={zh}
                      />
                      <ComparisonTable rows={metricRows} zh={zh} />
                    </div>
                  )}
                  {tab === "returns" && (
                    <div className="compare-content">
                      <div className="compare-toolbar">
                        <span>{zh ? "收益口径" : "Return basis"}</span>
                        <button
                          type="button"
                          className={returnMode === "net" ? "active" : ""}
                          onClick={() => setReturnMode("net")}
                        >
                          {zh ? "净收益" : "Net"}
                        </button>
                        <button
                          type="button"
                          className={returnMode === "gross" ? "active" : ""}
                          onClick={() => setReturnMode("gross")}
                        >
                          {zh ? "毛收益" : "Gross"}
                        </button>
                      </div>
                      <ComparisonChart
                        title={
                          returnMode === "net"
                            ? zh
                              ? "净收益累计"
                              : "Cumulative net return"
                            : zh
                              ? "毛收益算术累计"
                              : "Cumulative gross return"
                        }
                        rows={cumulativeSeries(
                          visible,
                          selectedTopN,
                          returnMode,
                        )}
                        series={chartSeries}
                        zh={zh}
                      />
                      <ComparisonChart
                        title={zh ? "净值回撤" : "Net drawdown"}
                        rows={drawdownRows(visible, selectedTopN)}
                        series={chartSeries}
                        zh={zh}
                      />
                      <ComparisonTable rows={metricRows} zh={zh} />
                    </div>
                  )}
                  {tab === "periods" && (
                    <div className="compare-content">
                      <div className="compare-toolbar">
                        <span>{zh ? "时间维度" : "Period"}</span>
                        {(["year", "quarter", "month"] as const).map((unit) => (
                          <button
                            type="button"
                            key={unit}
                            className={periodUnit === unit ? "active" : ""}
                            onClick={() => setPeriodUnit(unit)}
                          >
                            {unit === "year"
                              ? zh
                                ? "分年"
                                : "Year"
                              : unit === "quarter"
                                ? zh
                                  ? "分季度"
                                  : "Quarter"
                                : zh
                                  ? "分月"
                                  : "Month"}
                          </button>
                        ))}
                      </div>
                      <div className="compare-table-wrap">
                        <table className="compare-table">
                          <thead>
                            <tr>
                              <th>{zh ? "时间" : "Period"}</th>
                              <th>{zh ? "交易日" : "Days"}</th>
                              <th>A · {zh ? "净收益" : "Net return"}</th>
                              <th>B · {zh ? "净收益" : "Net return"}</th>
                              <th>{zh ? "差值 B − A" : "Difference B − A"}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {periodComparison(
                              visible,
                              selectedTopN,
                              periodUnit,
                            ).map((row) => (
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
                                      className={
                                        row.b >= row.a ? "positive" : "negative"
                                      }
                                    />
                                    {percent(row.b - row.a)}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                  {tab === "quality" && (
                    <div className="compare-content">
                      <div className="compare-toolbar">
                        <span>{zh ? "信号走势" : "Signal trend"}</span>
                        <select
                          value={qualityKey}
                          onChange={(event) =>
                            setQualityKey(event.target.value)
                          }
                        >
                          {qualityMetrics.map((metric) => (
                            <option key={metric.key} value={metric.key}>
                              {metric.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <ComparisonChart
                        title={`${qualityMetrics.find((metric) => metric.key === qualityKey)?.label || qualityKey} · MA20`}
                        rows={rollingQuality(visible, qualityKey)}
                        series={chartSeries.map((series) => ({
                          ...series,
                          format: "precise",
                        }))}
                        zh={zh}
                        percentAxis={false}
                      />
                      <ComparisonTable
                        rows={[
                          ...qualityMetrics.map((metric) => {
                            const mean = pairedMean(visible, metric.key);
                            return {
                              label: `${metric.label} ${zh ? "均值" : "mean"}`,
                              a: mean.a,
                              b: mean.b,
                              format: (value: number) =>
                                decimal(value, metric.digits),
                            };
                          }),
                          ...(["ic", "rank_ic"] as const).map((key) => {
                            const ratio = pairedRatio(
                              visible,
                              key,
                              annualizationDays,
                            );
                            return {
                              label: key === "ic" ? "ICIR" : "RankICIR",
                              a: ratio.a,
                              b: ratio.b,
                              format: (value: number) => decimal(value, 2),
                            };
                          }),
                        ]}
                        zh={zh}
                      />
                    </div>
                  )}
                  {tab === "trading" && (
                    <div className="compare-content">
                      <ComparisonTable
                        rows={[
                          metricRows[5],
                          {
                            label: zh ? "平均日交易成本" : "Average daily cost",
                            a:
                              statsA.turnover *
                              (taskA.settings.transactionCost ?? NaN),
                            b:
                              statsB.turnover *
                              (taskB.settings.transactionCost ?? NaN),
                            format: percent,
                          },
                        ]}
                        zh={zh}
                      />
                      <ComparisonChart
                        title={zh ? "每日换手率" : "Daily turnover"}
                        rows={visible.map((point) => ({
                          date: point.date,
                          a: point.a[`top${selectedTopN}_turnover`],
                          b: point.b[`top${selectedTopN}_turnover`],
                        }))}
                        series={chartSeries}
                        zh={zh}
                      />
                      <section className="viz-card compare-holdings">
                        <header>
                          <div>
                            <small>TOP 30 HOLDINGS</small>
                            <h3>{zh ? "持仓对照" : "Holdings comparison"}</h3>
                          </div>
                          <label>
                            {zh ? "交易日" : "Trading day"}
                            <select
                              value={activeDay?.date || ""}
                              onChange={(event) =>
                                setHoldingDate(event.target.value)
                              }
                            >
                              {visible.map((point) => (
                                <option key={point.date} value={point.date}>
                                  {point.date}
                                </option>
                              ))}
                            </select>
                          </label>
                        </header>
                        <div className="compare-overlap">
                          <strong>
                            {zh ? "共同持仓" : "Shared holdings"}{" "}
                            {overlap.common.length}
                          </strong>
                          <span>
                            {zh ? "重合度" : "Overlap"} {percent(overlap.ratio)}
                          </span>
                          <span>
                            A {zh ? "独有" : "only"} {overlap.onlyA.length}
                          </span>
                          <span>
                            B {zh ? "独有" : "only"} {overlap.onlyB.length}
                          </span>
                        </div>
                        <div className="compare-holdings-grid">
                          {([holdingsA, holdingsB] as const).map(
                            (holdings, index) => (
                              <div key={index}>
                                <h4>{index === 0 ? "A" : "B"} · Top 30</h4>
                                <div className="compare-table-wrap">
                                  <table className="compare-table">
                                    <thead>
                                      <tr>
                                        <th>#</th>
                                        <th>{zh ? "代码" : "Code"}</th>
                                        <th>{zh ? "名称" : "Name"}</th>
                                        <th>
                                          {zh ? "当日收益" : "Daily return"}
                                        </th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {holdings.map((item) => (
                                        <tr
                                          key={item.ts_code}
                                          className={
                                            overlap.common.includes(
                                              item.ts_code,
                                            )
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
                            ),
                          )}
                        </div>
                      </section>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </main>
      </div>
    </section>
  );
}
