import {
  AlertTriangle,
  ArrowLeftRight,
  CalendarDays,
  GitCompareArrows,
  LoaderCircle,
  RefreshCw,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../../shared/hooks/useAsyncResource";
import type { TaskSummary } from "../../tasks/types";
import { parseSourceTasks } from "../../../shared/lib/sourceTasks";
import { getResearchTask, listResearchTasks } from "../api";
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
  executionCostRates,
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

const EMPTY_TASKS: TaskSummary[] = [];

type CompareTab = "overview" | "returns" | "periods" | "quality" | "trading";
const numeric = (value: unknown) => {
  const number = finite(value);
  return Number.isFinite(number) ? number : NaN;
};
const percent = (value: number | null) =>
  value !== null && Number.isFinite(value)
    ? `${(value * 100).toFixed(2)}%`
    : "—";
const decimal = (value: number, digits = 3) =>
  Number.isFinite(value) ? value.toFixed(digits) : "—";
const dateInput = (value: string) =>
  `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
const compactDate = (value: string) => value.replaceAll("-", "");

function comparisonSettings(task: BacktestArtifact | null) {
  return {
    ...executionCostRates(task?.input_params || {}),
    annualizationDays: numeric(task?.input_params.annualization_days),
    riskFreeRate: numeric(task?.input_params.annual_risk_free_rate),
  };
}

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
    equityA *= 1 + numeric(point.a[`top${topN}_net_return`]);
    equityB *= 1 + numeric(point.b[`top${topN}_net_return`]);
    peakA = Math.max(peakA, equityA);
    peakB = Math.max(peakB, equityB);
    return { date: point.date, a: equityA / peakA - 1, b: equityB / peakB - 1 };
  });
}

export default function StrategyComparePage({
  target,
  initialTaskId,
  onConnection,
}: {
  target?: string;
  initialTaskId?: string;
  onConnection: (online: boolean) => void;
}) {
  const { t, i18n } = useTranslation();
  const zh = i18n.resolvedLanguage === "zh";
  const locale = zh ? "zh-CN" : "en-US";

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
  const loadList = useCallback(
    async (signal: AbortSignal) => {
      try {
        const summaries = await listResearchTasks("backtest", target, signal);
        signal.throwIfAborted();
        onConnection(true);
        return summaries;
      } catch (error) {
        if (!signal.aborted) onConnection(false);
        throw error;
      }
    },
    [target, onConnection],
  );
  const {
    data: summaries,
    loading: listLoading,
    error: listError,
    reload: reloadList,
  } = useAsyncResource(loadList);
  const tasks = summaries ?? EMPTY_TASKS;

  const [universeA, setUniverseA] = useState("");
  const [universeB, setUniverseB] = useState("");
  const loadSelected = useCallback(
    async (signal: AbortSignal) => {
      const ids = [idA, idB].filter((id) =>
        tasks.some((task) => task.task_id === id),
      );
      return Promise.all(
        [...new Set(ids)].map((id) =>
          getResearchTask("backtest", id, target, signal),
        ),
      );
    },
    [idA, idB, tasks, target],
  );
  const {
    data: selectedTasks,
    error: detailError,
    loading: detailLoading,
  } = useAsyncResource(loadSelected);
  const taskA = selectedTasks?.find((task) => task.task_id === idA) || null;
  const taskB = selectedTasks?.find((task) => task.task_id === idB) || null;
  const settingsA = comparisonSettings(taskA);
  const settingsB = comparisonSettings(taskB);
  const selectedA = taskA?.output_params.universes[universeA]
    ? universeA
    : taskA?.output_params.default_universe || "";
  const selectedB = taskB?.output_params.universes[universeB]
    ? universeB
    : taskB?.output_params.default_universe || "";
  const reportA = taskA?.output_params.universes[selectedA];
  const reportB = taskB?.output_params.universes[selectedB];
  const pair = `${idA}:${selectedA}\n${idB}:${selectedB}`;
  useEffect(() => {
    if (detailLoading || !taskA || !taskB || idA === idB) {
      setDailyA([]);
      setDailyB([]);
      setDataError("");
      setDataLoading(false);
      setLoadedPair("");
      return;
    }
    const controller = new AbortController();
    setDataLoading(true);
    setDataError("");
    Promise.all([
      loadBacktestDaily(taskA, selectedA, target, controller.signal),
      loadBacktestDaily(taskB, selectedB, target, controller.signal),
    ])
      .then(([a, b]) => {
        if (controller.signal.aborted) return;
        setDailyA(a);
        setDailyB(b);
        setLoadedPair(pair);
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
  }, [
    taskA,
    taskB,
    detailLoading,
    idA,
    idB,
    selectedA,
    selectedB,
    pair,
    target,
    onConnection,
  ]);

  const commonTopNs =
    taskA && taskB
      ? (reportA?.dimensions.top_ns || []).filter((n) =>
          (reportB?.dimensions.top_ns || []).includes(n),
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
    Number.isFinite(settingsA.annualizationDays) &&
    settingsA.annualizationDays === settingsB.annualizationDays
      ? settingsA.annualizationDays!
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
  const localizeStart = (rows: ChartRow[]) =>
    rows.map((row) =>
      row.date === "__start__" ? { ...row, date: t("common.start") } : row,
    );
  const availableTasks = tasks.filter((task) =>
    `${task.task_id} ${task.display_name}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const tabs: CompareTab[] = [
    "overview",
    "returns",
    "periods",
    "quality",
    "trading",
  ];
  const warnings: string[] = [];
  if (taskA && taskB) {
    if (
      [reportA, reportB].some(
        (report) => report?.evaluation_status === "incomplete_market_data",
      )
    )
      warnings.push(t("backtest.incomplete_market_data"));
    if (
      taskA.output_params.protocol?.version !==
      taskB.output_params.protocol?.version
    )
      warnings.push(t("compare.accounting_protocols_differ"));
    if (
      (["buyCost", "sellCost"] as const).some(
        (side) =>
          Number.isFinite(settingsA[side]) &&
          Number.isFinite(settingsB[side]) &&
          settingsA[side] !== settingsB[side],
      )
    )
      warnings.push(t("compare.transaction_costs_differ"));
    if (
      Number.isFinite(settingsA.annualizationDays) &&
      Number.isFinite(settingsB.annualizationDays) &&
      settingsA.annualizationDays !== settingsB.annualizationDays
    )
      warnings.push(t("compare.annualization_differs_comparison_uses_252"));
    if (
      parseSourceTasks(taskA.input_params.source_tasks).join() !==
      parseSourceTasks(taskB.input_params.source_tasks).join()
    )
      warnings.push(t("compare.prediction_sources_differ"));
    if (dailyA.length !== points.length || dailyB.length !== points.length)
      warnings.push(t("compare.only_shared_days_with_valid"));
  }
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
    <section className="workspace-page strategy-compare-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">RESEARCH / COMPARE</p>
          <h1>{t("compare.strategy_comparison")}</h1>
          <span>{t("compare.compare_backtests_on_shared_trading")}</span>
        </div>
      </div>
      <div className="compare-layout">
        <aside className="compare-picker rail-panel run-index">
          <header className="run-index-header rail-header">
            <div className="run-index-heading rail-heading">
              <small>TASK VERSIONS</small>
              <strong>{t("compare.task_versions")}</strong>
            </div>
            <div className="run-index-tools">
              <em>{tasks.length}</em>
              <button
                type="button"
                className="run-index-refresh rail-refresh"
                onClick={() => void reloadList()}
                aria-label={t("compare.refresh_tasks")}
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
              placeholder={t("compare.search_task_id")}
            />
          </label>
          <div className="compare-picker-list rail-scroll">
            <p className="compare-picker-hint">
              {t("compare.click_two_versions_to_compare")}
            </p>
            {listLoading && (
              <p className="compare-state">
                <LoaderCircle className="spin" />
                {t("compare.loading_tasks")}
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
                {t("compare.no_backtests_available")}
              </p>
            )}
            {availableTasks.map((task) => (
              <article
                className={
                  idA === task.task_id || idB === task.task_id ? "active" : ""
                }
                key={task.task_id}
              >
                <button
                  className="run-main rail-list-item compare-run-item"
                  type="button"
                  aria-pressed={idA === task.task_id || idB === task.task_id}
                  onClick={() => toggleTask(task.task_id)}
                >
                  <span className="run-item-avatar rail-avatar run-kind-backtest">
                    {task.reg_name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="rail-item-copy">
                    <strong>{task.reg_name}</strong>
                    <code title={task.task_id}>{task.task_id}</code>
                    <small>
                      {task.created_at
                        ? new Date(task.created_at).toLocaleString(locale)
                        : t("compare.metadata_unavailable")}
                    </small>
                  </span>
                  <span
                    className={`compare-slot-badge${idA === task.task_id ? " slot-a" : idB === task.task_id ? " slot-b" : ""}`}
                  >
                    {idA === task.task_id
                      ? "A"
                      : idB === task.task_id
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
                <div className="compare-selected-copy">
                  <small>{t("compare.backtest_task")}</small>
                  <strong title={task?.task_id}>
                    {task?.task_id || t("compare.choose_from_the_list")}
                  </strong>
                  {task && (
                    <label className="compare-universe">
                      <span>{t("backtest.universe")}</span>
                      <select
                        aria-label={`${t("backtest.universe")} ${index === 0 ? "A" : "B"}`}
                        value={index === 0 ? selectedA : selectedB}
                        onChange={(event) =>
                          (index === 0 ? setUniverseA : setUniverseB)(
                            event.target.value,
                          )
                        }
                      >
                        {Object.entries(task.output_params.universes).map(
                          ([key, report]) => (
                            <option key={key} value={key}>
                              {report.label}
                            </option>
                          ),
                        )}
                      </select>
                    </label>
                  )}
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
                setUniverseA(selectedB);
                setUniverseB(selectedA);
              }}
              aria-label={t("compare.swap_a_and_b")}
            >
              <ArrowLeftRight />
            </button>
          </div>
          {dataError || detailError ? (
            <div className="compare-empty error" role="alert">
              <AlertTriangle />
              <strong>{t("compare.unable_to_load_backtests")}</strong>
              <span>{dataError || detailError}</span>
            </div>
          ) : detailLoading ||
            (taskA && taskB && (dataLoading || loadedPair !== pair)) ? (
            <div className="compare-empty">
              <LoaderCircle className="spin" />
              <strong>{t("compare.calculating_shared_window")}</strong>
            </div>
          ) : !taskA || !taskB ? (
            <div className="compare-empty">
              <GitCompareArrows />
              <strong>{t("compare.select_two_backtests_to_compare")}</strong>
              <span>
                {tasks.length === 1
                  ? t("compare.only_one_backtest_is_available")
                  : t("compare.click_two_task_versions_on")}
              </span>
            </div>
          ) : !commonTopNs.length ? (
            <div className="compare-empty error">
              <AlertTriangle />
              <strong>{t("compare.no_shared_top_n")}</strong>
            </div>
          ) : !points.length ? (
            <div className="compare-empty error">
              <CalendarDays />
              <strong>{t("compare.no_shared_valid_trading_days")}</strong>
            </div>
          ) : (
            <>
              <div className="compare-controls">
                <div className="compare-window">
                  <CalendarDays />
                  <div>
                    <small>{t("compare.shared_window")}</small>
                    <strong>
                      {points[0].date} — {points.at(-1)?.date} · {points.length}{" "}
                      {t("compare.days")}
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
                  {t("compare.from")}
                  <input
                    type="date"
                    min={dateInput(points[0].date)}
                    max={dateInput(points.at(-1)!.date)}
                    value={from}
                    onChange={(event) => setFrom(event.target.value)}
                  />
                </label>
                <label>
                  {t("compare.to")}
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
                    {t("compare.reset_dates")}
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
                  <strong>{t("compare.no_shared_days_in_this")}</strong>
                </div>
              ) : (
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
                              {t("compare.difference")}{" "}
                              {metric.format(metric.b - metric.a)}
                            </em>
                          </article>
                        ))}
                      </div>
                      <ComparisonChart
                        title={t("compare.cumulative_net_return_shared_start")}
                        rows={localizeStart(
                          cumulativeSeries(visible, selectedTopN),
                        )}
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
                        <span>{t("compare.signal_trend")}</span>
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
                            a: pairedMean(
                              visible,
                              `top${selectedTopN}_transaction_cost`,
                            ).a,
                            b: pairedMean(
                              visible,
                              `top${selectedTopN}_transaction_cost`,
                            ).b,
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
                            {t("compare.shared_holdings")}{" "}
                            {overlap.common.length}
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
                          {([holdingsA, holdingsB] as const).map(
                            (holdings, index) => (
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
