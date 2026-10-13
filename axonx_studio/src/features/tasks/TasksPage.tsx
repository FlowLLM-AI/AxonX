import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Ban,
  CheckSquare2,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePolling } from "../../shared/hooks/usePolling";
import type { ContextOption } from "../../app/types";
import type { TaskSummary } from "./types";
import { cancelTask, deleteTasks, listTaskStatuses } from "./api";
import {
  ACTIVE,
  ATTENTION,
  STATES,
  groupTasks,
  type StateFilter,
} from "./groups";
import { TaskGroup, GroupSelection } from "./TaskGroup";

export function TasksPage({
  target,
  onSubmit,
  onOpenTask,
  onTasksChange,
  onConnection,
}: {
  target?: string;
  onSubmit: () => void;
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
  const [cancelTarget, setCancelTarget] = useState<TaskSummary | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectionMode, setSelectionMode] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    task: TaskSummary;
    x: number;
    y: number;
  } | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const request = useRef<AbortController | null>(null);
  const lifetime = useRef<AbortController | null>(null);

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
        const selectable = new Set(
          result
            .filter((task) => !ACTIVE.has(task.state))
            .map((task) => task.task_id),
        );
        setSelected(
          (previous) =>
            new Set([...previous].filter((taskId) => selectable.has(taskId))),
        );
        setError("");
        onConnection(true);
      } catch (reason) {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
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
    lifetime.current = controller;
    setTasks([]);
    setSelected(new Set());
    setSelectionMode(false);
    setContextMenu(null);
    setCancelTarget(null);
    setCancelling(false);
    setDeleteOpen(false);
    setDeleting(false);
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
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("click", close);
    window.addEventListener("blur", close);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("blur", close);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", close, true);
    };
  }, [contextMenu]);
  const poll = useCallback((signal: AbortSignal) => load(true, signal), [load]);
  const seconds = usePolling(poll, autoRefresh, 5);

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
  const selectableIds = filtered
    .filter((task) => !ACTIVE.has(task.state))
    .map((task) => task.task_id);
  const selectedIds = [...selected];
  const toggleTasks = (ids: string[]) =>
    setSelected((previous) => {
      const next = new Set(previous);
      const remove = ids.every((id) => next.has(id));
      ids.forEach((id) => (remove ? next.delete(id) : next.add(id)));
      return next;
    });

  const beginSelection = (task: TaskSummary) => {
    if (ACTIVE.has(task.state)) return;
    setSelectionMode(true);
    setSelected((previous) => new Set(previous).add(task.task_id));
    setContextMenu(null);
  };

  const finishSelection = () => {
    setSelectionMode(false);
    setSelected(new Set());
  };

  const confirmCancel = async () => {
    const signal = lifetime.current?.signal;
    if (!cancelTarget || !signal || signal.aborted) return;
    setCancelling(true);
    try {
      const cancelled = await cancelTask(cancelTarget.run_id, target);
      if (signal.aborted) return;
      if (!cancelled) throw new Error(t("cancelFailed"));
      setCancelTarget(null);
      await load(true, signal, true);
    } catch (reason) {
      if (signal.aborted) return;
      setCancelTarget(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (!signal.aborted) setCancelling(false);
    }
  };

  const confirmDelete = async () => {
    const signal = lifetime.current?.signal;
    if (!selectedIds.length || !signal || signal.aborted) return;
    const requested = selectedIds;
    setDeleting(true);
    try {
      const deleted = await deleteTasks(requested, target);
      if (signal.aborted) return;
      setSelected((previous) => {
        const next = new Set(previous);
        deleted.forEach((taskId) => next.delete(taskId));
        return next;
      });
      if (deleted.length === requested.length) setSelectionMode(false);
      setDeleteOpen(false);
      await load(true, signal, true);
      if (signal.aborted) return;
      if (deleted.length !== requested.length)
        throw new Error(
          t("deletePartial", {
            deleted: deleted.length,
            total: requested.length,
          }),
        );
    } catch (reason) {
      if (signal.aborted) return;
      setDeleteOpen(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (!signal.aborted) setDeleting(false);
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
          {selectionMode && (
            <div className="task-selection-actions">
              <span>{t("selectedCount", { count: selected.size })}</span>
              <button
                className="danger-outline"
                onClick={() => setDeleteOpen(true)}
                disabled={!selected.size}
              >
                <Trash2 size={14} />
                {t("confirmDelete")}
              </button>
              <button className="secondary-button" onClick={finishSelection}>
                <X size={14} />
                {t("finishSelection")}
              </button>
            </div>
          )}
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

      <div className="data-panel task-groups-panel">
        <div className="task-group-toolbar">
          {selectionMode ? (
            <GroupSelection
              ids={selectableIds}
              selected={selected}
              onToggle={toggleTasks}
              label={t("taskGroups.selectFiltered")}
            />
          ) : (
            <button
              className="secondary-button"
              onClick={() => setSelectionMode(true)}
              aria-label={t("enableMultiSelect")}
            >
              <CheckSquare2 size={16} />
            </button>
          )}
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
                {tasks.filter((task) => task.task_type === value).length}
              </option>
            ))}
          </select>
          <select
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
          </select>
        </div>
        <div className="task-groups" key={target || "local"}>
          {groups.map((group) => (
            <TaskGroup
              key={group.key}
              group={group}
              filterKey={filterKey}
              selectionMode={selectionMode}
              selected={selected}
              onToggle={toggleTasks}
              onOpenTask={onOpenTask}
              onContextMenu={(task, event) => {
                event.preventDefault();
                setContextMenu({
                  task,
                  x: Math.max(
                    6,
                    Math.min(event.clientX, window.innerWidth - 224),
                  ),
                  y: Math.max(
                    6,
                    Math.min(event.clientY, window.innerHeight - 240),
                  ),
                });
              }}
            />
          ))}
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
      {contextMenu && (
        <div
          className="workspace-context-menu task-context-menu"
          role="menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <header>
            <span>{contextMenu.task.task_id}</span>
            <small>{t(`types.${contextMenu.task.task_type}`)}</small>
          </header>
          <button
            role="menuitem"
            onClick={() => {
              onOpenTask(contextMenu.task.task_id);
              setContextMenu(null);
            }}
          >
            <Search />
            {t("details")}
          </button>
          {!ACTIVE.has(contextMenu.task.state) && (
            <button
              role="menuitem"
              onClick={() => beginSelection(contextMenu.task)}
            >
              <CheckSquare2 />
              {t("enableMultiSelect")}
            </button>
          )}
          {ACTIVE.has(contextMenu.task.state) && (
            <button
              className="danger"
              role="menuitem"
              onClick={() => {
                setCancelTarget(contextMenu.task);
                setContextMenu(null);
              }}
            >
              <Ban />
              {t("cancel")}
            </button>
          )}
        </div>
      )}
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
