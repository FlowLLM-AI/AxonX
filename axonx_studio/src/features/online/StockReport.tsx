import { Select } from "../../shared/ui/Select";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import {
  activeCommits,
  reportIsCurrent,
  type OnlineHistory,
  type StockOnlineReport,
  type ReportTab,
} from "./report";
import { ArtifactTableCache } from "./artifactCache";
import { loadHistory } from "./api";
import { CommitReport, CommitProvenance } from "./CommitReport";

export function StockReport({
  report,
  target,
  runtime,
  selection,
  flat = false,
}: {
  report: StockOnlineReport;
  target?: string;
  runtime: ReactNode;
  selection?: { date: string; slot: string; history: OnlineHistory | null };
  flat?: boolean;
}) {
  const { t } = useTranslation();
  const cache = useMemo(
    () => new ArtifactTableCache(report.commit.task_id, target),
    [target, report.commit.task_id],
  );
  useEffect(() => () => cache.clear(), [cache]);
  const [tab, setTab] = useState<ReportTab>("signal");
  const [commitId, setCommitId] = useState("");
  const [provenance, setProvenance] = useState(false);
  const suppliedHistory = selection?.history;
  const embedded = !!selection;
  const load = useCallback(
    (signal: AbortSignal) =>
      embedded
        ? Promise.resolve(suppliedHistory || null)
        : loadHistory(report.commit.task_id, target, signal),
    [report.commit, target, embedded, suppliedHistory],
  );
  const { data: history, error, loading, reload } = useAsyncResource(load);
  const active = history ? activeCommits(history) : [report.commit];
  const [date, setDate] = useState("");
  const [slot, setSlot] = useState("");
  const selectedDate =
    selection?.date ||
    date ||
    active.at(-1)?.trade_date ||
    report.commit.trade_date;
  const dated = active.filter((c) => c.trade_date === selectedDate);
  const selectedSlot =
    selection?.slot ||
    (dated.some((c) => c.trade_time === slot)
      ? slot
      : dated.at(-1)?.trade_time);
  const effective = dated.find((c) => c.trade_time === selectedSlot);
  const commit =
    history?.commits.find(
      (c) =>
        c.commit_id === commitId &&
        c.trade_date === effective?.trade_date &&
        c.trade_time === effective?.trade_time,
    ) || effective;
  const tabs: ReportTab[] = [
    "signal",
    "portfolio",
    "performance",
    "history",
    ...(runtime ? ["runtime" as const] : []),
  ];
  return (
    <div className="stock-online-report">
      {!selection && (
        <div className="online-report-toolbar">
          <label>
            {t("onlineWorkbench.date")}
            <input
              type="date"
              aria-label={t("onlineWorkbench.date")}
              value={`${selectedDate.slice(0, 4)}-${selectedDate.slice(4, 6)}-${selectedDate.slice(6)}`}
              onChange={(event) => {
                if (event.target.value) {
                  setDate(event.target.value.replaceAll("-", ""));
                  setCommitId("");
                }
              }}
            />
          </label>
          <label>
            {t("onlineWorkbench.slot")}
            <Select
              aria-label={t("onlineWorkbench.slot")}
              value={selectedSlot || ""}
              onChange={(event) => {
                setSlot(event.target.value);
                setCommitId("");
              }}
            >
              {dated.map((c) => (
                <option key={c.commit_id} value={c.trade_time}>
                  {c.trade_time.slice(0, 2)}:{c.trade_time.slice(2)}
                </option>
              ))}
            </Select>
          </label>
        </div>
      )}
      {!flat && (
        <nav className="backtest-tabs" aria-label={t("onlineReport.tabsLabel")}>
          {tabs.map((key) => (
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
      )}
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
      ) : !commit ? (
        <p className="empty-state">{t("onlineWorkbench.noSignal")}</p>
      ) : (
        <>
          {commit.commit_id !== effective?.commit_id && (
            <div className="online-warning" role="status">
              {t("onlineWorkbench.oldRevision")}
              <button type="button" onClick={() => setCommitId("")}>
                {t("onlineWorkbench.returnEffective")}
              </button>
            </div>
          )}
          {history && !reportIsCurrent(history, commit) && (
            <div className="online-warning" role="status">
              {t("onlineReport.stale")}
            </div>
          )}
          {tab === "history" && history ? (
            <RevisionHistory
              history={
                selection
                  ? {
                      ...history,
                      commits: history.commits.filter(
                        (c) =>
                          c.trade_date === selection.date &&
                          c.trade_time === selection.slot,
                      ),
                    }
                  : history
              }
              selected={commit.commit_id}
              onSelect={(id) => {
                setCommitId(id);
                const selected = history.commits.find(
                  (item) => item.commit_id === id,
                );
                if (!selection && selected) {
                  setDate(selected.trade_date);
                  setSlot(selected.trade_time);
                }
                setTab("signal");
              }}
            />
          ) : (
            <CommitReport
              cache={cache}
              key={`${target}:${commit.commit_id}:${tab}`}
              commit={commit}
              history={history}
              tab={flat ? "signal" : tab}
              target={target}
            />
          )}
          {!flat && (
            <div className="online-provenance-action">
              <button
                type="button"
                className="secondary-button"
                aria-expanded={provenance}
                onClick={() => setProvenance((value) => !value)}
              >
                {t("onlineReport.tabs.provenance")}
              </button>
            </div>
          )}
          {provenance && (
            <section className="quality-inline-details">
              <CommitProvenance commit={commit} />
            </section>
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
            {new Date(commit.committed_at).toLocaleString()} ·{" "}
            {commit.started_at}
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
