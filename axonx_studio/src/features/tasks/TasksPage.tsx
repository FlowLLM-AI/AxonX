import { Select } from "../../shared/ui/Select";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, LoaderCircle, RefreshCw, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useRefresh } from "../../shared/hooks/useRefresh";
import type { ContextOption } from "../../app/types";
import type { TaskSummary } from "./types";
import { listTaskStatuses } from "./api";
import {
  ACTIVE,
  ATTENTION,
  STATES,
  groupTasks,
  type StateFilter,
  type TaskGroupData,
} from "./groups";
import { TaskGroup, TaskTableColumns, TaskTableHeading } from "./TaskGroup";

export function TasksPage({
  target,
  onOpenTask,
  onTasksChange,
  onConnection,
}: {
  target?: string;
  onOpenTask: (taskId: string) => void;
  onTasksChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<StateFilter>("");
  const [type, setType] = useState("");
  const request = useRef<AbortController | null>(null);

  const load = useCallback(
    async (quiet = false, signal?: AbortSignal, invalidate = false) => {
      if (signal?.aborted) return;
      if (invalidate) request.current?.abort();
      if (request.current && !request.current.signal.aborted) return;
      const controller = new AbortController();
      request.current = controller;
      const abort = () => controller.abort();
      signal?.addEventListener("abort", abort, { once: true });
      if (quiet) setRefreshing(true);
      else setLoading(true);
      try {
        const result = await listTaskStatuses(target, controller.signal);
        if (controller.signal.aborted) return;
        setTasks(result);
        setError("");
        onConnection(true);
      } catch (reason) {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
        controller.abort();
      } finally {
        signal?.removeEventListener("abort", abort);
        if (request.current === controller) {
          request.current = null;
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [onConnection, target],
  );

  useEffect(() => {
    const controller = new AbortController();
    setTasks([]);
    setError("");
    void load();
    return () => {
      controller.abort();
      request.current?.abort();
      request.current = null;
    };
  }, [load]);
  useEffect(() => {
    onTasksChange?.(
      tasks.map((task) => ({
        value: task.task_id,
        label: task.task_id,
        detail: task.reg_name || task.task_type,
      })),
    );
  }, [tasks, onTasksChange]);
  const poll = useCallback((signal: AbortSignal) => load(true, signal), [load]);
  const [seconds, setSeconds] = useState(60);
  const refreshNow = useRefresh(poll, autoRefresh, false, setSeconds);

  const types = useMemo(
    () => [...new Set(tasks.map((task) => task.task_type))].sort(),
    [tasks],
  );
  const groups = useMemo(
    () => groupTasks(tasks, { search, state, type }),
    [tasks, search, state, type],
  );
  const filtered = groups.flatMap((group) => group.tasks);
  const filterKey = JSON.stringify([search.trim().toLowerCase(), state, type]);
  const stats = {
    total: tasks.length,
    active: tasks.filter((item) => ACTIVE.has(item.state)).length,
    attention: tasks.filter((item) => ATTENTION.has(item.state)).length,
  };
  const renderGroup = (group: TaskGroupData) => (
    <TaskGroup
      key={group.key}
      group={group}
      filterKey={filterKey}
      onOpenTask={onOpenTask}
    />
  );

  return (
    <section className="workspace-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TASK RUNTIME / 01</p>
          <h1>{t("taskTitle")}</h1>
          <span>{t("taskLead")}</span>
        </div>
        <div className="heading-actions">
          <label className="auto-toggle" title={t("autoRefresh")}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
              aria-label={t("autoRefresh")}
            />
            <i />
            {autoRefresh && <small>{t("nextRefresh", { seconds })}</small>}
          </label>
          <button
            className="secondary-button"
            onClick={() => void refreshNow()}
            disabled={refreshing}
            title={t("refreshNow")}
            aria-label={t("refreshNow")}
          >
            <RefreshCw size={16} className={refreshing ? "spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>{t("requestFailed")}</strong>
            <span>
              {error} · {t("staleHint")}
            </span>
          </div>
          <button onClick={() => void load()}>{t("retry")}</button>
        </div>
      )}

      <div className="data-panel task-groups-panel">
        <div className="task-group-toolbar">
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label={t("search")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("search")}
            />
          </label>
          <span className="task-group-total">
            {t(
              filtered.length === tasks.length
                ? "taskGroups.total"
                : "taskGroups.matchingTotal",
              {
                groups: groups.length,
                count: filtered.length,
                total: tasks.length,
              },
            )}
          </span>
          <Select
            className="table-filter-select"
            aria-label={t("type")}
            value={type}
            onChange={(event) => setType(event.target.value)}
          >
            <option value="">
              {t("allTypes")} · {tasks.length}
            </option>
            {types.map((value) => (
              <option key={value} value={value}>
                {t(`types.${value}`, value)} ·{" "}
                {tasks.filter((task) => task.task_type === value).length}
              </option>
            ))}
          </Select>
          <Select
            className="table-filter-select"
            aria-label={t("state")}
            value={state}
            onChange={(event) => setState(event.target.value as StateFilter)}
          >
            <option value="">
              {t("allStates")} · {stats.total}
            </option>
            <option value="active">
              {t("active")} · {stats.active}
            </option>
            <option value="attention">
              {t("attention")} · {stats.attention}
            </option>
            {STATES.map((value) => (
              <option key={value} value={value}>
                {t(`states.${value}`)} ·{" "}
                {tasks.filter((task) => task.state === value).length}
              </option>
            ))}
          </Select>
        </div>
        <div className="task-groups" key={target || "local"}>
          {groups.length > 0 && (
            <div className="task-list-heading table-wrap" aria-hidden="true">
              <table>
                <TaskTableColumns />
                <TaskTableHeading />
              </table>
            </div>
          )}
          {groups.map(renderGroup)}
          {!loading && filtered.length === 0 && (
            <div className="empty-state">
              <span className="empty-glyph">⌁</span>
              <strong>
                {search || state || type ? t("noMatches") : t("noTasks")}
              </strong>
              <p>
                {search || state || type ? t("noMatches") : t("noTasksHint")}
              </p>
            </div>
          )}
          {loading && (
            <div className="loading-state">
              <LoaderCircle className="spin" /> {t("tasks.loadingRuntime")}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
