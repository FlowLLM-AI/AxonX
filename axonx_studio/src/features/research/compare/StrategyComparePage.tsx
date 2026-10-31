import {
  AlertTriangle,
  ArrowLeftRight,
  CalendarDays,
  GitCompareArrows,
  LoaderCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TaskSummary } from "../../../shared/api/contracts";
import { useAsyncResource } from "../../../shared/hooks/useAsyncResource";
import {
  compactDate,
  dateInput,
  toNumber as finite,
} from "../../../shared/lib/format";
import { upstreamTaskIds } from "../../../shared/lib/tasks";
import { PortfolioSelector } from "../PortfolioSelector";
import { getResearchTask, listResearchTasks } from "../api";
import { loadBacktestDaily } from "../backtest/api";
import type { BacktestArtifact, DailyRow } from "../backtest/types";
import { ComparisonReport } from "./ComparisonReport";
import { executionCostRates, pairDays, portfolioDaily } from "./model";

const EMPTY_TASKS: TaskSummary[] = [];

function comparisonSettings(task: BacktestArtifact | null) {
  return {
    ...executionCostRates(task?.input_params || {}),
    annualizationDays: finite(task?.input_params.annualization_days),
    riskFreeRate: finite(task?.input_params.annual_risk_free_rate),
  };
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
  const { t } = useTranslation();

  const [idA, setIdA] = useState(initialTaskId || "");
  const [idB, setIdB] = useState("");
  const [dailyA, setDailyA] = useState<DailyRow[]>([]);
  const [dailyB, setDailyB] = useState<DailyRow[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState("");
  const [loadedPair, setLoadedPair] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const toggleTask = (taskId: string) => {
    if (!idA) setIdA(taskId);
    else if (!idB) setIdB(taskId);
    else if (idA === taskId) setIdA("");
    else if (idB === taskId) setIdB("");
    else setIdB(taskId);
    setFrom("");
    setTo("");
  };

  useEffect(() => {
    if (initialTaskId) setIdA(initialTaskId);
  }, [initialTaskId]);
  const loadList = useCallback(
    async (signal: AbortSignal) => {
      try {
        const summaries = await listResearchTasks("backtest", {
          target,
          signal,
        });
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
          getResearchTask("backtest", id, { target, signal }),
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
  const selectedA = taskA?.output_params.portfolios[Number(universeA)]
    ? universeA
    : "0";
  const selectedB = taskB?.output_params.portfolios[Number(universeB)]
    ? universeB
    : "0";
  const reportA = taskA?.output_params.portfolios[Number(selectedA)];
  const reportB = taskB?.output_params.portfolios[Number(selectedB)];
  const pair = `${idA}:${selectedA}\n${idB}:${selectedB}`;
  useEffect(() => {
    if (detailLoading || !taskA || !taskB) {
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
      loadBacktestDaily(taskA, selectedA, {
        target,
        signal: controller.signal,
      }),
      loadBacktestDaily(taskB, selectedB, {
        target,
        signal: controller.signal,
      }),
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

  const selectedTopN = reportA?.dimensions.top_ns[0] || 1;
  const otherTopN = reportB?.dimensions.top_ns[0] || 1;
  const points = useMemo(
    () =>
      pairDays(
        dailyA,
        portfolioDaily(dailyB, otherTopN, selectedTopN),
        selectedTopN,
      ),
    [dailyA, dailyB, selectedTopN, otherTopN],
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
      upstreamTaskIds(taskA.input_params.upstream_task_ids).join() !==
      upstreamTaskIds(taskB.input_params.upstream_task_ids).join()
    )
      warnings.push(t("compare.prediction_sources_differ"));
    if (dailyA.length !== points.length || dailyB.length !== points.length)
      warnings.push(t("compare.only_shared_days_with_valid"));
  }

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
        <ComparisonPicker
          tasks={tasks}
          idA={idA}
          idB={idB}
          loading={listLoading}
          error={listError}
          onSelect={toggleTask}
          onRefresh={() => void reloadList()}
        />
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
                    <PortfolioSelector
                      label={`${t("backtest.portfolio")} ${index === 0 ? "A" : "B"}`}
                      portfolios={task.output_params.portfolios}
                      value={index === 0 ? selectedA : selectedB}
                      onChange={index === 0 ? setUniverseA : setUniverseB}
                    />
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
                  : t("compare.click_two_task_list_on")}
              </span>
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
                <span>
                  A: Top {selectedTopN} · B: Top {otherTopN}
                </span>
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
                <ComparisonReport
                  key={pair}
                  points={visible}
                  topN={selectedTopN}
                  annualizationDays={annualizationDays}
                />
              )}
            </>
          )}
        </main>
      </div>
    </section>
  );
}

import { ComparisonPicker } from "./ComparisonPicker";
