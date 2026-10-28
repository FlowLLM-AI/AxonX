import { Info } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { formatTableValue as display } from "../../shared/lib/format";
import { Select } from "../../shared/ui/Select";
import type { ArtifactTableCache } from "./artifactCache";
import { Performance } from "./Performance";
import {
  activeCommits,
  type OnlineCommit,
  type OnlineHistory,
  type ReportTab,
} from "./report";
import { ReportTable, type Column } from "./ReportTable";
import { SignalTable, type SignalFilters } from "./SignalTable";

export function CommitReport({
  commit,
  cache,
  history,
  tab,
}: {
  commit: OnlineCommit;
  cache: ArtifactTableCache;
  history?: OnlineHistory | null;
  tab: ReportTab;
}) {
  const { t } = useTranslation();
  const [signalFilters, setSignalFilters] = useState<SignalFilters>({
    buyableOnly: true,
  });
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
            [role, await cache.load(commit.artifacts[role], signal)] as const,
        ),
      );
      const previousRows =
        tab === "signal" && previous
          ? await cache.load(previous.artifacts.signal, signal)
          : [];
      return {
        tables: Object.fromEntries(tables),
        previousRows,
      };
    },
    [cache, commit, history, tab],
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
      {settings.evaluation_status !== "done" && (
        <div className="online-warning" role="status">
          {t("onlineReport.incomplete")}
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
            <Select
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
            >
              {settings.dimensions.top_ns.map((n) => (
                <option key={n} value={n}>
                  Top {n}
                </option>
              ))}
            </Select>
          </label>
          <span>{t("onlineReport.simulated")}</span>
          {settings.portfolio.missing_market_as_suspension === true && (
            <span className="online-assumption">
              <Info aria-hidden="true" />
              {t("onlineReport.suspensionAssumption")}
            </span>
          )}
          <small>
            {settings.date_range.start} → {settings.date_range.end}
          </small>
        </div>
      )}
      {tab === "signal" ? (
        <>
          <SignalTable
            filters={signalFilters}
            onFiltersChange={setSignalFilters}
            rows={tables.signal}
            previous={data.previousRows}
            scoreMethod={String(settings.score_selection.method)}
            recordedUniverse={settings.portfolio.universe}
          />
        </>
      ) : tab === "portfolio" ? (
        <>
          <div className="online-metrics">
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

export function CommitProvenance({ commit }: { commit: OnlineCommit }) {
  const { t } = useTranslation();
  const settings = commit.protocol.report;
  return (
    <section className="online-provenance">
      <h3>{t("onlineReport.provenance")}</h3>
      <div className="online-model">
        <span>
          <small>{t("onlineReport.commitId")}</small>
          <code>{commit.commit_id}</code>
        </span>
        <span>
          <small>{t("started")}</small>
          <code>{commit.started_at}</code>
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
    </section>
  );
}
