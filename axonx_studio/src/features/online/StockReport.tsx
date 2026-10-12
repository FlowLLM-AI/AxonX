import { useCallback, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import {
  activeCommits,
  reportIsCurrent,
  type OnlineHistory,
  type StockOnlineReport,
  type ReportTab,
} from "./report";
import { loadHistory } from "./api";
import { CommitReport } from "./CommitReport";

export function StockReport({
  report,
  target,
  runtime,
}: {
  report: StockOnlineReport;
  target?: string;
  runtime: ReactNode;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<ReportTab>("signal");
  const [commitId, setCommitId] = useState("");
  const load = useCallback(
    (signal: AbortSignal) => loadHistory(report.commit.task_id, target, signal),
    [report.commit.task_id, target],
  );
  const { data: history, error, loading, reload } = useAsyncResource(load);
  const commit =
    history?.commits.find((c) => c.commit_id === commitId) ||
    history?.commits.at(-1) ||
    report.commit;
  const active = history ? activeCommits(history) : [report.commit];
  const revisions = history?.commits.filter(
    (c) =>
      c.trade_date === commit.trade_date && c.trade_time === commit.trade_time,
  ) || [commit];
  return (
    <div className="stock-online-report">
      <nav className="backtest-tabs" aria-label={t("onlineReport.tabsLabel")}>
        {(
          [
            "signal",
            "portfolio",
            "performance",
            "history",
            "runtime",
          ] as ReportTab[]
        ).map((key) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
          >
            {t(`onlineReport.tabs.${key}`)}
          </button>
        ))}
      </nav>
      {tab === "runtime" ? (
        runtime
      ) : error ? (
        <div className="error-state" role="alert">
          {error}
          <button onClick={() => void reload()}>
            {t("onlinePipeline.refresh")}
          </button>
        </div>
      ) : loading && !history ? (
        <div className="loading-state">{t("shell.loading")}</div>
      ) : (
        <>
          <div className="online-report-toolbar">
            <label>
              {t("onlineReport.signalDate")}
              <select
                value={
                  active.find(
                    (c) =>
                      c.trade_date === commit.trade_date &&
                      c.trade_time === commit.trade_time,
                  )?.commit_id
                }
                onChange={(event) => setCommitId(event.target.value)}
              >
                {active.map((c) => (
                  <option key={c.commit_id} value={c.commit_id}>
                    {c.trade_date} · {c.trade_time}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("onlineReport.revision")}
              <select
                value={commit.commit_id}
                onChange={(event) => setCommitId(event.target.value)}
              >
                {revisions.map((c) => (
                  <option key={c.commit_id} value={c.commit_id}>
                    r{c.revision} · {new Date(c.committed_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <span className="online-status status-done">
              {t("onlineReport.committed")}
            </span>
          </div>
          {history && !reportIsCurrent(history, commit) && (
            <div className="online-warning" role="status">
              {t("onlineReport.stale")}
            </div>
          )}
          {tab === "history" && history ? (
            <RevisionHistory
              history={history}
              selected={commit.commit_id}
              onSelect={(id) => {
                setCommitId(id);
                setTab("signal");
              }}
            />
          ) : (
            <CommitReport
              key={`${target}:${commit.commit_id}:${tab}`}
              commit={commit}
              history={history}
              tab={tab}
              target={target}
            />
          )}
        </>
      )}
    </div>
  );
}
function RevisionHistory({
  history,
  selected,
  onSelect,
}: {
  history: OnlineHistory;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const active = new Set(activeCommits(history).map((c) => c.commit_id));
  return (
    <section className="online-history">
      <header>
        <p className="eyebrow">SIGNAL JOURNAL</p>
        <h3>{t("onlineReport.historyTitle")}</h3>
        <p>{t("onlineReport.historyHint")}</p>
      </header>
      {[...history.commits].reverse().map((commit) => (
        <button
          className={`online-revision ${selected === commit.commit_id ? "active" : ""}`}
          key={commit.commit_id}
          onClick={() => onSelect(commit.commit_id)}
        >
          <div>
            <strong>
              {commit.trade_date} · {commit.trade_time}
            </strong>
            <span
              className={`online-status status-${active.has(commit.commit_id) ? "done" : "skipped"}`}
            >
              {t(
                active.has(commit.commit_id)
                  ? "onlineReport.effective"
                  : "onlineReport.superseded",
              )}{" "}
              · r{commit.revision}
            </span>
          </div>
          <small>
            {new Date(commit.committed_at).toLocaleString()} · {commit.run_id}
          </small>
          <code>{commit.model_identity.models_sha256}</code>
          {!reportIsCurrent(history, commit) && (
            <small>{t("onlineReport.staleShort")}</small>
          )}
        </button>
      ))}
    </section>
  );
}
