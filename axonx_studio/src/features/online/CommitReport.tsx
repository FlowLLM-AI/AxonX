import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import {
  activeCommits,
  type OnlineCommit,
  type OnlineHistory,
  type ReportTab,
} from "./report";
import { loadRows } from "./api";
import { ReportTable, type Column } from "./ReportTable";
import { display } from "./format";
import { SignalTable } from "./SignalTable";
import { Performance } from "./Performance";

export function CommitReport({
  commit,
  history,
  tab,
  target,
}: {
  commit: OnlineCommit;
  history?: OnlineHistory | null;
  tab: ReportTab;
  target?: string;
}) {
  const { t } = useTranslation();
  const [topN, setTopN] = useState(commit.protocol.report.dimensions.top_ns[0]);
  const load = useCallback(
    async (signal: AbortSignal) => {
      const previous =
        history &&
        activeCommits({
          ...history,
          commits: history.commits.slice(
            0,
            history.commits.findIndex((c) => c.commit_id === commit.commit_id) +
              1,
          ),
        })
          .filter((c) => c.trade_date < commit.trade_date)
          .at(-1);
      const roles =
        tab === "signal"
          ? ["signal"]
          : tab === "portfolio"
            ? ["positions", "orders", "trades", "daily", "signal"]
            : ["daily", "summary"];
      const tables = await Promise.all(
        roles.map(
          async (role) =>
            [role, await loadRows(commit, role, target, signal)] as const,
        ),
      );
      const previousRows =
        tab === "signal" && previous
          ? await loadRows(previous, "signal", target, signal)
          : [];
      return { tables: Object.fromEntries(tables), previousRows };
    },
    [commit, history, tab, target],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  if (error)
    return (
      <div className="error-state" role="alert">
        {error}
        <button onClick={() => void reload()}>
          {t("onlinePipeline.refresh")}
        </button>
      </div>
    );
  if (loading || !data)
    return <div className="loading-state">{t("shell.loading")}</div>;
  const settings = commit.protocol.report;
  const tables = data.tables;
  const current = tables.daily?.find(
    (row) => row.trade_date === commit.trade_date,
  );
  const column = (key: string, format?: Column["format"]): Column => ({
    key,
    label: t(`onlineReport.columns.${key}`),
    format,
  });
  const nRows = (role: string) =>
    (tables[role] || []).filter((row) => row.top_n === topN);
  return (
    <>
      {(settings.evaluation_status !== "done" ||
        settings.portfolio.missing_market_as_suspension === true) && (
        <div className="online-warning" role="status">
          {settings.evaluation_status !== "done"
            ? t("onlineReport.incomplete")
            : t("onlineReport.suspensionAssumption")}
          {settings.missing_dates.length > 0 && (
            <span>
              {t("onlineReport.missingDates")}:{" "}
              {settings.missing_dates.join(", ")}
            </span>
          )}
        </div>
      )}
      {tab !== "signal" && (
        <div className="online-report-toolbar">
          <label>
            {t("onlineReport.strategy")}
            <select
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
            >
              {settings.dimensions.top_ns.map((n) => (
                <option key={n} value={n}>
                  Top {n}
                </option>
              ))}
            </select>
          </label>
          <span>{t("onlineReport.simulated")}</span>
          <small>
            {settings.date_range.start} → {settings.date_range.end}
          </small>
        </div>
      )}
      {tab === "signal" ? (
        <>
          <div className="online-summary online-kpis">
            <Kpi
              label={t("onlinePipeline.metrics.candidate_count")}
              value={tables.signal.length}
            />
            <Kpi
              label={t("onlineReport.buyableCount")}
              value={
                tables.signal.filter((row) => row.is_buyable_at_signal).length
              }
            />
            <Kpi
              label={t("onlineReport.selection")}
              value={t(
                `onlineReport.methods.${String(settings.score_selection.method)}`,
                String(settings.score_selection.method || "—"),
              )}
            />
            <Kpi
              label={t("onlineReport.revision")}
              value={`r${commit.revision}`}
            />
          </div>
          <SignalTable rows={tables.signal} previous={data.previousRows} />
        </>
      ) : tab === "portfolio" ? (
        <>
          <div className="online-summary online-kpis">
            <Kpi
              label={t("onlineReport.netValue")}
              value={display(current?.[`top${topN}_net_value`], "score")}
            />
            <Kpi
              label={t("onlineReport.cashWeight")}
              value={display(current?.[`top${topN}_cash_weight`], "percent")}
            />
            <Kpi
              label={t("onlineReport.positionCount")}
              value={current?.[`top${topN}_count`]}
            />
            <Kpi
              label={t("onlineReport.turnover")}
              value={display(current?.[`top${topN}_turnover`], "percent")}
            />
          </div>
          <h3>{t("onlineReport.positions")}</h3>
          <ReportTable
            rows={nRows("positions")
              .filter((row) => row.trade_date === commit.trade_date)
              .map((row) => ({
                ...row,
                name: tables.signal.find((s) => s.ts_code === row.ts_code)
                  ?.name,
              }))}
            columns={[
              column("ts_code"),
              column("name"),
              column("entry_date"),
              column("planned_exit_date"),
              column("weight", "percent"),
              column("market_value", "score"),
              column("exit_delayed"),
            ]}
          />
          <h3>{t("onlineReport.orders")}</h3>
          <ReportTable
            rows={nRows("orders").filter(
              (row) => row.trade_date === commit.trade_date,
            )}
            columns={[
              column("ts_code"),
              column("side"),
              column("status"),
              column("reason"),
              column("notional", "score"),
              column("fee", "score"),
            ]}
          />
          <h3>{t("onlineReport.trades")}</h3>
          <ReportTable
            rows={nRows("trades")}
            columns={[
              column("ts_code"),
              column("entry_date"),
              column("exit_date"),
              column("realized_return", "percent"),
              column("fee", "score"),
            ]}
          />
        </>
      ) : (
        <Performance
          key={topN}
          rows={tables.daily}
          summary={tables.summary}
          topN={topN}
          benchmarks={settings.dimensions.benchmarks}
        />
      )}
      <details className="online-provenance">
        <summary>{t("onlineReport.provenance")}</summary>
        <div className="online-model">
          <span>
            <small>{t("onlineReport.commitId")}</small>
            <code>{commit.commit_id}</code>
          </span>
          <span>
            <small>Run ID</small>
            <code>{commit.run_id}</code>
          </span>
          {Object.entries(commit.model_identity).map(([key, value]) => (
            <span key={key}>
              <small>{key}</small>
              <code>{value}</code>
            </span>
          ))}
          <span>
            <small>{t("onlineReport.strategyId")}</small>
            <code>{settings.strategy_identity}</code>
          </span>
          <pre>{JSON.stringify(settings.portfolio, null, 2)}</pre>
        </div>
      </details>
    </>
  );
}
function Kpi({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{display(value)}</strong>
    </div>
  );
}
