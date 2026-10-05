import { useCallback, useState } from "react";
import { Activity, ArrowUpRight, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { listTaskStatuses } from "../tasks/api";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { usePolling } from "../../shared/hooks/usePolling";
import type { TaskStatus } from "../tasks/types";
import { loadOnlineReport } from "./api";
import { isOnlineTask, type OnlineOutcome } from "./types";
import { playground } from "../../app/environment";

export default function OnlinePage({
  target,
  initialTaskId,
  onSelected,
  onConnection,
  onOpenTask,
}: {
  target?: string;
  initialTaskId?: string;
  onSelected: (id: string) => void;
  onConnection: (online: boolean) => void;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const tasks = await listTaskStatuses(target, signal);
        if (!signal.aborted) onConnection(true);
        return tasks
          .filter(isOnlineTask)
          .sort((a, b) =>
            (b.created_at || "").localeCompare(a.created_at || ""),
          );
      } catch (error) {
        if (!signal.aborted) onConnection(false);
        throw error;
      }
    },
    [target, onConnection],
  );
  const { data, loading, error, reload } = useAsyncResource(load);
  const tasks = (data || []).filter(
    (task) =>
      (filter === "all" || task.task_type === filter) &&
      `${task.task_id} ${task.config.task_name || task.task_name}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const selected =
    tasks.find((task) => task.task_id === initialTaskId) || tasks[0];
  const refresh = useCallback(async () => {
    await reload();
  }, [reload]);
  usePolling(
    refresh,
    !!data?.some((task) => ["running", "queued"].includes(task.state)),
    5,
  );
  return (
    <section className="workspace-page online-page">
      <header className="online-heading">
        <div>
          <p className="eyebrow">AXONX / LIVE</p>
          <h1>{t("onlinePipeline.title")}</h1>
          <p>{t("onlinePipeline.lead")}</p>
        </div>
        <button className="secondary-button" onClick={() => void reload()}>
          <RefreshCw />
          {t("onlinePipeline.refresh")}
        </button>
      </header>
      {playground && (
        <div className="online-demo">
          <Activity size={16} />
          {t("onlinePipeline.demo")}
        </div>
      )}
      <div className="online-filters">
        <div>
          {["all", "api", "inference", "analysis"].map((kind) => (
            <button
              key={kind}
              className={filter === kind ? "active" : ""}
              aria-pressed={filter === kind}
              onClick={() => setFilter(kind)}
            >
              {t(`onlinePipeline.kinds.${kind}`)}
            </button>
          ))}
        </div>
        <input
          aria-label={t("onlinePipeline.search")}
          placeholder={t("onlinePipeline.search")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      {error ? (
        <div className="error-state" role="alert">
          {error}
        </div>
      ) : loading && !data ? (
        <div className="loading-state">{t("shell.loading")}</div>
      ) : !tasks.length ? (
        <div className="empty-state">{t("onlinePipeline.empty")}</div>
      ) : (
        <div className="online-layout">
          <aside className="online-runs">
            {tasks.map((task) => (
              <button
                key={task.task_id}
                className={selected?.task_id === task.task_id ? "active" : ""}
                aria-pressed={selected?.task_id === task.task_id}
                onClick={() => onSelected(task.task_id)}
              >
                <span>
                  {t(`onlinePipeline.kinds.${task.task_type}`)}
                  <Status value={task.state} />
                </span>
                <strong>
                  {String(task.config.task_name || task.task_name)}
                </strong>
                <small>{task.task_id}</small>
              </button>
            ))}
          </aside>
          {selected && (
            <RunReport
              key={`${target}:${selected.task_id}`}
              task={selected}
              target={target}
              onOpenTask={onOpenTask}
            />
          )}
        </div>
      )}
    </section>
  );
}

function Status({ value }: { value: string }) {
  const { t } = useTranslation();
  return (
    <span className={`online-status status-${value}`}>
      {t(`onlinePipeline.status.${value}`, value)}
    </span>
  );
}

function RunReport({
  task,
  target,
  onOpenTask,
}: {
  task: TaskStatus;
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const load = useCallback(
    (signal: AbortSignal) => loadOnlineReport(task, target, signal),
    [task, target],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  const rows = data?.windows || data?.comparisons || [];
  const done = rows.filter(
    (row) => row.status === "done" || row.status === "consistent",
  ).length;
  return (
    <article className="online-report">
      <header>
        <div>
          <p className="eyebrow">
            {t(`onlinePipeline.kinds.${task.task_type}`)}
          </p>
          <h2>{String(task.config.task_name || task.task_name)}</h2>
          <small>{task.task_id}</small>
        </div>
        <button
          className="secondary-button"
          onClick={() => onOpenTask(task.task_id)}
        >
          {t("onlinePipeline.openTask")}
          <ArrowUpRight />
        </button>
      </header>
      {task.error && (
        <div className="error-state" role="alert">
          {task.error}
        </div>
      )}
      <div className="online-summary">
        <div>
          <span>{t("onlinePipeline.runState")}</span>
          <Status value={task.state} />
        </div>
        <div>
          <span>{t("onlinePipeline.outcomes")}</span>
          <strong>{rows.length}</strong>
        </div>
        <div>
          <span>{t("onlinePipeline.complete")}</span>
          <strong>
            {done} / {rows.length}
          </strong>
        </div>
      </div>
      {data?.model_identity && (
        <div className="online-model">
          <strong>{t("onlinePipeline.model")}</strong>
          {Object.entries(data.model_identity).map(([key, value]) => (
            <span key={key}>
              <small>{key}</small>
              <code>{value}</code>
            </span>
          ))}
        </div>
      )}
      <h3>
        {t(
          task.task_type === "analysis"
            ? "onlinePipeline.comparisons"
            : "onlinePipeline.windows",
        )}
      </h3>
      {error ? (
        <div className="error-state" role="alert">
          {error}
          <button onClick={() => void reload()}>
            {t("onlinePipeline.refresh")}
          </button>
        </div>
      ) : loading && !data ? (
        <div className="loading-state">{t("shell.loading")}</div>
      ) : !rows.length ? (
        <div className="empty-state">{t("onlinePipeline.pending")}</div>
      ) : (
        rows.map((row) => <Outcome key={row.key} row={row} />)
      )}
    </article>
  );
}

function Outcome({ row }: { row: OnlineOutcome }) {
  const { t } = useTranslation();
  return (
    <section className="online-outcome">
      <header>
        <strong>{row.key}</strong>
        <Status value={row.status} />
      </header>
      <div className="online-metrics">
        {row.coverage != null && (
          <div>
            <span>{t("onlinePipeline.coverage")}</span>
            <strong>{(row.coverage * 100).toFixed(1)}%</strong>
            <progress max={1} value={row.coverage} />
          </div>
        )}
        {row.rows != null && (
          <div>
            <span>{t("onlinePipeline.rows")}</span>
            <strong>{row.rows.toLocaleString()}</strong>
          </div>
        )}
        {row.elapsed_seconds != null && (
          <div>
            <span>{t("onlinePipeline.elapsed")}</span>
            <strong>{row.elapsed_seconds.toFixed(1)}s</strong>
          </div>
        )}
        {Object.entries(row.metrics || {}).map(([key, value]) => (
          <div key={key}>
            <span>{t(`onlinePipeline.metrics.${key}`, key)}</span>
            <strong>
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value)}
            </strong>
          </div>
        ))}
      </div>
      {row.reason && (
        <p className="online-reason">
          {t(`onlinePipeline.reasons.${row.reason}`, row.reason)}
        </p>
      )}
    </section>
  );
}
