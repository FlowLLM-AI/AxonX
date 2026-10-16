import { canCancel, canDelete } from "./groups";
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
import type { Schedule, TaskSummary } from "./types";
import {
  cancelTask,
  deleteTasks,
  listTaskStatuses,
  listSchedules,
} from "./api";
import {
  ACTIVE,
  ATTENTION,
  STATES,
  groupTasks,
  type StateFilter,
  type TaskGroupData,
} from "./groups";
import {
  TaskGroup,
  GroupSelection,
  TaskTableColumns,
  TaskTableHeading,
} from "./TaskGroup";

import { ScheduleCard } from "./ScheduleCard";

type MenuTarget =
  { kind: "task"; task: TaskSummary } | { kind: "group"; groupKey: string };

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
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [tab, setTab] = useState<"scheduled" | "other">("other");
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
  const [contextMenu, setContextMenu] = useState<
    (MenuTarget & { x: number; y: number }) | null
  >(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    ids: string[];
    group?: string;
  } | null>(null);
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
        const [result, configuredSchedules] = await Promise.all([
          listTaskStatuses(target, controller.signal),
          listSchedules(target, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setTasks(result);
        setSchedules(configuredSchedules);
        const selectable = new Set(
          result.filter(canDelete).map((task) => task.task_id),
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
    lifetime.current = controller;
    setTasks([]);
    setSchedules([]);
    setSelected(new Set());
    setSelectionMode(false);
    setContextMenu(null);
    setCancelTarget(null);
    setCancelling(false);
    setDeleteTarget(null);
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
  const seconds = usePolling(poll, autoRefresh);

  const visibleTasks = useMemo(
    () =>
      tasks.filter(
        (task) => Boolean(task.source.schedule) === (tab === "scheduled"),
      ),
    [tasks, tab],
  );
  const scheduleGroups = useMemo(() => {
    const scheduleKey = (name: string, id?: string | null) =>
      JSON.stringify([name, id ?? null]);
    const entries = new Map(
      schedules.map((schedule) => [
        scheduleKey(schedule.name, schedule.scheduler_id),
        { name: schedule.name, schedule: schedule as Schedule | null },
      ]),
    );
    for (const task of visibleTasks) {
      const source = task.source.schedule;
      if (!source) continue;
      const key = scheduleKey(source.name, source.scheduler_id);
      if (!entries.has(key))
        entries.set(key, { name: source.name, schedule: null });
    }
    const query = search.trim().toLowerCase();
    return [...entries]
      .flatMap(([key, { name, schedule }]) => {
        const matchesSchedule =
          `${name} ${schedule?.job ?? ""} ${schedule?.description ?? ""}`
            .toLowerCase()
            .includes(query);
        const members = visibleTasks.filter((task) => {
          const source = task.source.schedule;
          return (
            source && scheduleKey(source.name, source.scheduler_id) === key
          );
        });
        const filter = { search: matchesSchedule ? "" : search, state, type };
        const groups = groupTasks(members, filter).map((group) => ({
          ...group,
          key: JSON.stringify([key, group.key]),
          label: group.key,
        }));
        const active = groups.some((group) => group.active > 0);
        return groups.length || matchesSchedule
          ? [{ key, name, schedule, groups, active }]
          : [];
      })
      .sort((a, b) => Number(b.active) - Number(a.active));
  }, [schedules, visibleTasks, search, state, type]);
  const types = useMemo(
    () => [...new Set(visibleTasks.map((task) => task.task_type))].sort(),
    [visibleTasks],
  );
  const groups = useMemo(
    () =>
      tab === "scheduled"
        ? scheduleGroups.flatMap((entry) => entry.groups)
        : groupTasks(visibleTasks, { search, state, type }),
    [tab, scheduleGroups, visibleTasks, search, state, type],
  );
  const filtered = groups.flatMap((group) => group.tasks);
  const filterKey = JSON.stringify([search.trim().toLowerCase(), state, type]);
  const stats = {
    total: visibleTasks.length,
    active: visibleTasks.filter((item) => ACTIVE.has(item.state)).length,
    attention: visibleTasks.filter((item) => ATTENTION.has(item.state)).length,
  };
  const selectableIds = filtered.filter(canDelete).map((task) => task.task_id);
  const selectedIds = [...selected];
  const terminalIds = new Set(
    tasks.filter(canDelete).map((task) => task.task_id),
  );
  const deleteIds = (deleteTarget?.ids || []).filter((id) =>
    terminalIds.has(id),
  );
  const menuGroup =
    contextMenu?.kind === "group"
      ? groups.find((group) => group.key === contextMenu.groupKey)
      : undefined;
  const groupIds = (menuGroup?.tasks || [])
    .filter(canDelete)
    .map((task) => task.task_id);
  const openContextMenu = (
    item: MenuTarget,
    event: React.MouseEvent<HTMLElement>,
  ) => {
    event.preventDefault();
    setContextMenu({
      ...item,
      x: Math.max(6, Math.min(event.clientX, window.innerWidth - 224)),
      y: Math.max(6, Math.min(event.clientY, window.innerHeight - 240)),
    });
  };
  const toggleTasks = (ids: string[]) =>
    setSelected((previous) => {
      const next = new Set(previous);
      const remove = ids.every((id) => next.has(id));
      ids.forEach((id) => (remove ? next.delete(id) : next.add(id)));
      return next;
    });

  const beginSelection = (task: TaskSummary) => {
    if (!canDelete(task)) return;
    setSelectionMode(true);
    setSelected((previous) => new Set(previous).add(task.task_id));
    setContextMenu(null);
  };

  const finishSelection = () => {
    setSelectionMode(false);
    setSelected(new Set());
  };

  const changeTab = (value: "scheduled" | "other") => {
    if (tab === value) return;
    setTab(value);
    finishSelection();
    setContextMenu(null);
    setSearch("");
    setState("");
    setType("");
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
    if (!deleteIds.length || !signal || signal.aborted) return;
    const requested = deleteIds;
    setDeleting(true);
    try {
      const deleted = await deleteTasks(requested, target);
      if (signal.aborted) return;
      setSelected((previous) => {
        const next = new Set(previous);
        deleted.forEach((taskId) => next.delete(taskId));
        return next;
      });
      if (selectedIds.every((id) => deleted.includes(id)))
        setSelectionMode(false);
      setDeleteTarget(null);
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
      setDeleteTarget(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (!signal.aborted) setDeleting(false);
    }
  };

  const renderGroup = (group: TaskGroupData) => (
    <TaskGroup
      key={group.key}
      group={group}
      separateHistory={tab === "scheduled"}
      showHistory={Boolean(search || state || type)}
      filterKey={filterKey}
      selectionMode={selectionMode}
      selected={selected}
      onToggle={toggleTasks}
      onOpenTask={onOpenTask}
      onGroupContextMenu={(event) =>
        openContextMenu({ kind: "group", groupKey: group.key }, event)
      }
      onContextMenu={(task, event) =>
        openContextMenu({ kind: "task", task }, event)
      }
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
          {selectionMode && (
            <div className="task-selection-actions">
              <span>{t("selectedCount", { count: selected.size })}</span>
              <button
                className="danger-outline"
                onClick={() => setDeleteTarget({ ids: selectedIds })}
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

      <div
        className="task-runtime-tabs"
        role="tablist"
        aria-label={t("taskTitle")}
      >
        {(["scheduled", "other"] as const).map((value) => (
          <button
            key={value}
            role="tab"
            id={`tasks-tab-${value}`}
            aria-controls="tasks-panel"
            aria-selected={tab === value}
            tabIndex={tab === value ? 0 : -1}
            onClick={() => changeTab(value)}
            onKeyDown={(event) => {
              const next =
                event.key === "Home"
                  ? "scheduled"
                  : event.key === "End"
                    ? "other"
                    : event.key === "ArrowLeft" || event.key === "ArrowRight"
                      ? value === "scheduled"
                        ? "other"
                        : "scheduled"
                      : null;
              if (!next) return;
              event.preventDefault();
              changeTab(next);
              document.getElementById(`tasks-tab-${next}`)?.focus();
            }}
          >
            {t(`schedules.tabs.${value}`)}
          </button>
        ))}
      </div>
      <div
        id="tasks-panel"
        role="tabpanel"
        aria-labelledby={`tasks-tab-${tab}`}
        className="data-panel task-groups-panel"
      >
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
              aria-label={t(
                tab === "scheduled" ? "schedules.search" : "search",
              )}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t(
                tab === "scheduled" ? "schedules.search" : "search",
              )}
            />
          </label>
          <span className="task-group-total">
            {t(
              tab === "scheduled"
                ? "schedules.total"
                : filtered.length === visibleTasks.length
                  ? "taskGroups.total"
                  : "taskGroups.matchingTotal",
              {
                groups: groups.length,
                schedules: scheduleGroups.length,
                count: filtered.length,
                total: visibleTasks.length,
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
              {t("allTypes")} · {visibleTasks.length}
            </option>
            {types.map((value) => (
              <option key={value} value={value}>
                {t(`types.${value}`, value)} ·{" "}
                {visibleTasks.filter((task) => task.task_type === value).length}
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
                {visibleTasks.filter((task) => task.state === value).length}
              </option>
            ))}
          </select>
        </div>
        <div className="task-groups" key={target || "local"}>
          {tab === "other" && groups.length > 0 && (
            <div className="task-list-heading table-wrap" aria-hidden="true">
              <table>
                <TaskTableColumns selectionMode={selectionMode} />
                <TaskTableHeading selectionMode={selectionMode} />
              </table>
            </div>
          )}
          {tab === "scheduled"
            ? scheduleGroups.map((entry) => (
                <ScheduleCard
                  key={entry.key}
                  name={entry.name}
                  schedule={entry.schedule}
                >
                  {!entry.active && (
                    <p className="muted">{t("schedules.noActiveTasks")}</p>
                  )}
                  {entry.groups.map(renderGroup)}
                </ScheduleCard>
              ))
            : groups.map(renderGroup)}
          {!loading &&
            filtered.length === 0 &&
            (tab !== "scheduled" || !scheduleGroups.length) && (
              <div className="empty-state">
                <span className="empty-glyph">⌁</span>
                <strong>
                  {search || state || type
                    ? t("noMatches")
                    : t(
                        tab === "scheduled"
                          ? "schedules.emptyTitle"
                          : "noTasks",
                      )}
                </strong>
                <p>
                  {search || state || type
                    ? t("noMatches")
                    : t(
                        tab === "scheduled"
                          ? "schedules.emptyHint"
                          : "noTasksHint",
                      )}
                </p>
                {!visibleTasks.length && tab === "other" && (
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
      {contextMenu && (contextMenu.kind === "task" || menuGroup) && (
        <div
          className="workspace-context-menu task-context-menu"
          role="menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          {contextMenu.kind === "group" ? (
            <>
              <header>
                <span>{menuGroup?.label || contextMenu.groupKey}</span>
                <small>
                  {t("taskGroups.terminalCount", { count: groupIds.length })}
                </small>
              </header>
              <button
                role="menuitem"
                disabled={!groupIds.length}
                onClick={() => {
                  setSelectionMode(true);
                  setSelected(
                    (previous) => new Set([...previous, ...groupIds]),
                  );
                  setContextMenu(null);
                }}
              >
                <CheckSquare2 />
                {t("taskGroups.selectMembers")}
              </button>
              <button
                className="danger"
                role="menuitem"
                disabled={!groupIds.length}
                onClick={() => {
                  setDeleteTarget({
                    ids: groupIds,
                    group: menuGroup?.label || contextMenu.groupKey,
                  });
                  setContextMenu(null);
                }}
              >
                <Trash2 />
                {t("taskGroups.deleteMembers")}
              </button>
            </>
          ) : (
            <>
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
              {canDelete(contextMenu.task) && (
                <button
                  role="menuitem"
                  onClick={() => beginSelection(contextMenu.task)}
                >
                  <CheckSquare2 />
                  {t("enableMultiSelect")}
                </button>
              )}
              {canCancel(contextMenu.task) && !contextMenu.task.is_replica && (
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
            </>
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
      {deleteTarget && (
        <div
          className="modal-backdrop"
          onMouseDown={() => setDeleteTarget(null)}
        >
          <div
            className="confirm-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <button
              className="close-button"
              onClick={() => setDeleteTarget(null)}
            >
              <X />
            </button>
            <span className="danger-icon">
              <Trash2 />
            </span>
            <h2>
              {t(
                deleteTarget.group
                  ? "taskGroups.deleteConfirm"
                  : "deleteConfirm",
                {
                  count: deleteIds.length,
                },
              )}
            </h2>
            {deleteTarget.group && <code>{deleteTarget.group}</code>}
            <p>{t("deleteHint")}</p>
            <div>
              <button
                className="secondary-button"
                onClick={() => setDeleteTarget(null)}
              >
                {t("close")}
              </button>
              <button
                className="danger-button"
                onClick={() => void confirmDelete()}
                disabled={deleting || !deleteIds.length}
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
