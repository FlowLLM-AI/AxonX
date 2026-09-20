import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Ban,
  Check,
  Copy,
  GitBranch,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import { usePolling } from "../../shared/hooks/usePolling";
import type { ContextOption } from "../../app/types";
import type { TaskState, TaskStatus } from "./types";
import { cancelTask, deleteTasks, listTaskStatuses } from "./api";
import { formatDate, formatDuration, taskStepProgress } from "./format";

const ACTIVE = new Set<TaskState>(["queued", "running"]);
const ATTENTION = new Set<TaskState>(["failed", "cancelled"]);

export function TasksPage({
  remoteIp,
  onSubmit,
  onOpenTask,
  onOpenGraph,
  onTasksChange,
  onConnection,
}: {
  remoteIp?: string;
  onSubmit: () => void;
  onOpenTask: (taskId: string) => void;
  onOpenGraph: (taskId: string) => void;
  onTasksChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<TaskStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<"" | "active" | "attention" | TaskState>(
    "",
  );
  const [type, setType] = useState("");
  const [cancelTarget, setCancelTarget] = useState<TaskStatus | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(
    async (quiet = false) => {
      if (quiet) setRefreshing(true);
      else setLoading(true);
      try {
        const result = await listTaskStatuses(remoteIp);
        const ordered = [...result].sort(
          (left, right) => taskTimestamp(right) - taskTimestamp(left),
        );
        setTasks(ordered);
        setSelected(
          (previous) =>
            new Set(
              [...previous].filter((taskId) =>
                ordered.some(
                  (task) => task.task_id === taskId && !ACTIVE.has(task.state),
                ),
              ),
            ),
        );
        setError("");
        onConnection(true);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [onConnection, remoteIp],
  );

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    onTasksChange?.(
      tasks.map((task) => ({
        value: task.task_id,
        label: task.task_id,
        detail: task.task_name || task.task_type,
      })),
    );
  }, [tasks, onTasksChange]);
  const poll = useCallback(() => {
    void load(true);
  }, [load]);
  const seconds = usePolling(poll, autoRefresh, 2);

  const types = useMemo(
    () => [...new Set(tasks.map((task) => task.task_type))].sort(),
    [tasks],
  );
  const filtered = useMemo(
    () =>
      tasks.filter((task) => {
        const query = search.trim().toLowerCase();
        const matches =
          !query ||
          `${task.task_id} ${task.task_type} ${task.pid || ""}`
            .toLowerCase()
            .includes(query);
        const matchesState =
          !state ||
          (state === "active" && ACTIVE.has(task.state)) ||
          (state === "attention" && ATTENTION.has(task.state)) ||
          task.state === state;
        return matches && matchesState && (!type || task.task_type === type);
      }),
    [tasks, search, state, type],
  );
  const stats = {
    total: tasks.length,
    active: tasks.filter((item) => ACTIVE.has(item.state)).length,
    attention: tasks.filter((item) => ATTENTION.has(item.state)).length,
  };
  const selectableIds = filtered
    .filter((task) => !ACTIVE.has(task.state))
    .map((task) => task.task_id);
  const selectedIds = [...selected];
  const allVisibleSelected =
    selectableIds.length > 0 &&
    selectableIds.every((taskId) => selected.has(taskId));

  const toggleAllVisible = () =>
    setSelected((previous) => {
      const next = new Set(previous);
      if (allVisibleSelected)
        selectableIds.forEach((taskId) => next.delete(taskId));
      else selectableIds.forEach((taskId) => next.add(taskId));
      return next;
    });

  const toggleTask = (taskId: string) =>
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });

  const confirmCancel = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      const cancelled = await cancelTask(cancelTarget.task_id, remoteIp);
      if (!cancelled) throw new Error(t("cancelFailed"));
      setCancelTarget(null);
      await load(true);
    } catch (reason) {
      setCancelTarget(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCancelling(false);
    }
  };

  const confirmDelete = async () => {
    if (!selectedIds.length) return;
    const requested = selectedIds;
    setDeleting(true);
    try {
      const deleted = await deleteTasks(requested, remoteIp);
      setSelected((previous) => {
        const next = new Set(previous);
        deleted.forEach((taskId) => next.delete(taskId));
        return next;
      });
      setDeleteOpen(false);
      await load(true);
      if (deleted.length !== requested.length)
        throw new Error(
          t("deletePartial", {
            deleted: deleted.length,
            total: requested.length,
          }),
        );
    } catch (reason) {
      setDeleteOpen(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDeleting(false);
    }
  };

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
            onClick={() => void load(true)}
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

      <div className="data-panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="select-column">
                  <input
                    type="checkbox"
                    aria-label={t("selectAll")}
                    checked={allVisibleSelected}
                    disabled={!selectableIds.length}
                    onChange={toggleAllVisible}
                  />
                </th>
                <th className="task-filter-column">
                  <div className="table-search-head">
                    <span>{t("taskId")}</span>
                    <label className="search-field">
                      <Search size={15} />
                      <input
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder={t("search")}
                      />
                    </label>
                    <small>
                      {filtered.length} / {tasks.length}
                    </small>
                  </div>
                </th>
                <th className="type-column">
                  <select
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
                        {
                          tasks.filter((task) => task.task_type === value)
                            .length
                        }
                      </option>
                    ))}
                  </select>
                </th>
                <th className="state-column">
                  <select
                    className="table-filter-select"
                    aria-label={t("state")}
                    value={state}
                    onChange={(event) =>
                      setState(
                        event.target.value as
                          "" | "active" | "attention" | TaskState,
                      )
                    }
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
                    {Object.entries(
                      t("states", { returnObjects: true }) as Record<
                        string,
                        string
                      >,
                    ).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label} ·{" "}
                        {tasks.filter((task) => task.state === key).length}
                      </option>
                    ))}
                  </select>
                </th>
                <th className="progress-column">{t("progress")}</th>
                <th className="started-column">{t("started")}</th>
                <th className="duration-column">{t("duration")}</th>
                <th className="action-column">
                  {selected.size > 0 ? (
                    <button
                      className="danger-outline bulk-delete"
                      onClick={() => setDeleteOpen(true)}
                    >
                      <Trash2 size={14} />
                      {selected.size}
                    </button>
                  ) : (
                    t("action")
                  )}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((task) => (
                <TaskRow
                  key={task.task_id}
                  task={task}
                  selected={selected.has(task.task_id)}
                  onSelect={() => toggleTask(task.task_id)}
                  onOpen={() => onOpenTask(task.task_id)}
                  onOpenGraph={() => onOpenGraph(task.task_id)}
                  onCancel={() => setCancelTarget(task)}
                />
              ))}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <div className="empty-state">
              <span className="empty-glyph">⌁</span>
              <strong>{tasks.length ? t("noMatches") : t("noTasks")}</strong>
              <p>{tasks.length ? t("noMatches") : t("noTasksHint")}</p>
              {!tasks.length && (
                <button className="primary-button" onClick={onSubmit}>
                  <Plus size={17} />
                  {t("pages.submit")}
                </button>
              )}
            </div>
          )}
          {loading && (
            <div className="loading-state">
              <LoaderCircle className="spin" /> {t("tasks.loadingRuntime")}
            </div>
          )}
        </div>
      </div>
      {cancelTarget && (
        <div
          className="modal-backdrop"
          onMouseDown={() => setCancelTarget(null)}
        >
          <div
            className="confirm-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <button
              className="close-button"
              onClick={() => setCancelTarget(null)}
            >
              <X />
            </button>
            <span className="danger-icon">
              <Ban />
            </span>
            <h2>{t("cancelConfirm")}</h2>
            <code>{cancelTarget.task_id}</code>
            <div>
              <button
                className="secondary-button"
                onClick={() => setCancelTarget(null)}
              >
                {t("close")}
              </button>
              <button
                className="danger-button"
                onClick={() => void confirmCancel()}
                disabled={cancelling}
              >
                {cancelling ? t("cancelling") : t("confirmCancel")}
              </button>
            </div>
          </div>
        </div>
      )}
      {deleteOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={() => setDeleteOpen(false)}
        >
          <div
            className="confirm-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <button
              className="close-button"
              onClick={() => setDeleteOpen(false)}
            >
              <X />
            </button>
            <span className="danger-icon">
              <Trash2 />
            </span>
            <h2>{t("deleteConfirm", { count: selected.size })}</h2>
            <p>{t("deleteHint")}</p>
            <div>
              <button
                className="secondary-button"
                onClick={() => setDeleteOpen(false)}
              >
                {t("close")}
              </button>
              <button
                className="danger-button"
                onClick={() => void confirmDelete()}
                disabled={deleting}
              >
                {deleting ? t("deleting") : t("confirmDelete")}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function taskTimestamp(task: TaskStatus) {
  const value = task.started_at || task.created_at || task.finished_at;
  if (value) return new Date(value).getTime();
  const compact = task.task_id.split("#")[3];
  if (!/^\d{10}(?:\d{4})?$/.test(compact || "")) return 0;
  const iso = `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}T${compact.slice(8, 10)}:${compact.slice(10, 12) || "00"}:${compact.slice(12, 14) || "00"}Z`;
  return new Date(iso).getTime();
}

function TaskRow({
  task,
  selected,
  onSelect,
  onOpen,
  onOpenGraph,
  onCancel,
}: {
  task: TaskStatus;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
  onOpenGraph: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const progress = taskStepProgress(task);
  const selectable = !ACTIVE.has(task.state);
  const clipboard = useCopyFeedback();
  const copied = clipboard.copied === task.task_id;
  return (
    <tr className={selected ? "selected" : ""} onClick={onOpen}>
      <td
        className="select-column"
        onClick={(event) => event.stopPropagation()}
      >
        <input
          type="checkbox"
          aria-label={t("selectTask", { taskId: task.task_id })}
          checked={selected}
          disabled={!selectable}
          onChange={onSelect}
        />
      </td>
      <td className="task-id-column">
        <div className="task-identity">
          <span className={`task-orb ${task.state}`}>
            {task.task_type.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <span className="task-id-line">
              <strong title={task.task_id}>{task.task_id}</strong>
              <button
                type="button"
                className={copied ? "copied" : ""}
                aria-label={copied ? t("copied") : t("copyTaskId")}
                title={copied ? t("copied") : t("copyTaskId")}
                onClick={(event) => {
                  event.stopPropagation();
                  void clipboard.copy(task.task_id);
                }}
              >
                {copied ? (
                  <>
                    <Check />
                    <span aria-live="polite">{t("copied")}</span>
                  </>
                ) : (
                  <Copy />
                )}
              </button>
            </span>
            <small>PID {task.pid || "—"}</small>
          </div>
        </div>
      </td>
      <td className="type-column">
        <span className="type-chip">
          {t(`types.${task.task_type}`, task.task_type)}
        </span>
      </td>
      <td className="state-column">
        <Status state={task.state} />
      </td>
      <td className="progress-column">
        {progress ? (
          <div className="progress-cell">
            <span className="progress-step">
              <small>{t("step")}</small>
              <strong>{progress.current}</strong>
            </span>
            <span
              className="progress-ring"
              style={
                {
                  "--step-progress": `${progress.percentage}%`,
                } as React.CSSProperties
              }
            >
              <strong>{progress.percentage}</strong>
              <small>%</small>
            </span>
          </div>
        ) : (
          <span className="muted">{t("notStarted")}</span>
        )}
      </td>
      <td className="started-column">
        {formatDate(task.started_at || task.created_at)}
      </td>
      <td className="duration-column">{formatDuration(task, t)}</td>
      <td className="action-column">
        <div className="row-actions">
          <button
            className="task-graph-action"
            onClick={(event) => {
              event.stopPropagation();
              onOpenGraph();
            }}
            aria-label={t("tasks.locateRelationshipsWithId", {
              taskId: task.task_id,
            })}
            title={t("tasks.locateRelationships")}
          >
            <GitBranch />
          </button>
          {ACTIVE.has(task.state) && (
            <button
              className="text-danger"
              onClick={(event) => {
                event.stopPropagation();
                onCancel();
              }}
            >
              {t("cancel")}
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

export function Status({ state }: { state: TaskState }) {
  const { t } = useTranslation();
  return (
    <span className={`status-badge ${state}`}>
      <i />
      {t(`states.${state}`)}
    </span>
  );
}
