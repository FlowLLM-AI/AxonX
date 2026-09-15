import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Ban, Check, ChevronRight, Copy, LoaderCircle, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { cancelTask, deleteTasks, listTaskStatuses } from "./api";
import { interpolate, t } from "./i18n";
import { formatDate, formatDuration, taskStepProgress } from "./taskFormat";
import type { ContextOption, Language, TaskState, TaskStatus } from "./types";

const ACTIVE = new Set<TaskState>(["queued", "running"]);
const ATTENTION = new Set<TaskState>(["failed", "cancelled"]);

export function TasksPage({ language, remoteIp, onSubmit, onOpenTask, onTasksChange, onConnection }: { language: Language; remoteIp?: string; onSubmit: () => void; onOpenTask: (taskId: string) => void; onTasksChange?: (options: ContextOption[]) => void; onConnection: (online: boolean) => void }) {
  const text = t(language);
  const [tasks, setTasks] = useState<TaskStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [seconds, setSeconds] = useState(10);
  const [search, setSearch] = useState("");
  const [state, setState] = useState<"" | "active" | "attention" | TaskState>("");
  const [type, setType] = useState("");
  const [cancelTarget, setCancelTarget] = useState<TaskStatus | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await listTaskStatuses(remoteIp);
      const ordered = [...result].sort((left, right) => taskTimestamp(right) - taskTimestamp(left));
      setTasks(ordered);
      setSelected((previous) => new Set([...previous].filter((taskId) => ordered.some((task) => task.task_id === taskId && !ACTIVE.has(task.state)))));
      setError(""); onConnection(true); setSeconds(10);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false);
    } finally { setLoading(false); setRefreshing(false); }
  }, [onConnection, remoteIp]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { onTasksChange?.(tasks.map((task) => ({ value: task.task_id, label: task.task_id, detail: task.task_name || task.task_type }))); }, [tasks, onTasksChange]);
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => setSeconds((value) => {
      if (value <= 1) { void load(true); return 10; }
      return value - 1;
    }), 1000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, load]);

  const types = useMemo(() => [...new Set(tasks.map((task) => task.task_type))].sort(), [tasks]);
  const filtered = useMemo(() => tasks.filter((task) => {
    const query = search.trim().toLowerCase();
    const matches = !query || `${task.task_id} ${task.task_type} ${task.pid || ""}`.toLowerCase().includes(query);
    const matchesState = !state
      || state === "active" && ACTIVE.has(task.state)
      || state === "attention" && ATTENTION.has(task.state)
      || task.state === state;
    return matches && matchesState && (!type || task.task_type === type);
  }), [tasks, search, state, type]);
  const stats = {
    total: tasks.length,
    active: tasks.filter((item) => ACTIVE.has(item.state)).length,
    attention: tasks.filter((item) => ATTENTION.has(item.state)).length,
  };
  const selectableIds = filtered.filter((task) => !ACTIVE.has(task.state)).map((task) => task.task_id);
  const selectedIds = [...selected];
  const allVisibleSelected = selectableIds.length > 0 && selectableIds.every((taskId) => selected.has(taskId));

  const toggleAllVisible = () => setSelected((previous) => {
    const next = new Set(previous);
    if (allVisibleSelected) selectableIds.forEach((taskId) => next.delete(taskId));
    else selectableIds.forEach((taskId) => next.add(taskId));
    return next;
  });

  const toggleTask = (taskId: string) => setSelected((previous) => {
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
      if (!cancelled) throw new Error(text.cancelFailed);
      setCancelTarget(null);
      await load(true);
    }
    catch (reason) {
      setCancelTarget(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally { setCancelling(false); }
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
      if (deleted.length !== requested.length) throw new Error(interpolate(text.deletePartial, { deleted: deleted.length, total: requested.length }));
    } catch (reason) {
      setDeleteOpen(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setDeleting(false); }
  };

  return <section className="workspace-page">
    <div className="page-heading">
      <div><p className="eyebrow">TASK RUNTIME / 01</p><h1>{text.taskTitle}</h1><span>{text.taskLead}</span></div>
      <div className="heading-actions">
        <label className="auto-toggle"><input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} /><i /><span>{text.autoRefresh}<small>{autoRefresh ? interpolate(text.nextRefresh, { seconds }) : "—"}</small></span></label>
        <button className="secondary-button" onClick={() => void load(true)} disabled={refreshing}><RefreshCw size={16} className={refreshing ? "spin" : ""} />{text.refreshNow}</button>
        <button className="primary-button" onClick={onSubmit}><Plus size={17} />{text.pages.submit}</button>
      </div>
    </div>

    {error && <div className="error-banner"><AlertTriangle size={18} /><div><strong>{text.requestFailed}</strong><span>{error} · {text.staleHint}</span></div><button onClick={() => void load()}>{text.retry}</button></div>}

    <div className="data-panel">
      <div className="table-wrap">
        <table><thead><tr><th className="select-column"><input type="checkbox" aria-label={text.selectAll} checked={allVisibleSelected} disabled={!selectableIds.length} onChange={toggleAllVisible} /></th><th className="task-filter-column"><div className="table-search-head"><span>{text.taskId}</span><label className="search-field"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={text.search} /></label><small>{filtered.length} / {tasks.length}</small></div></th><th className="type-column"><select className="table-filter-select" aria-label={text.type} value={type} onChange={(event) => setType(event.target.value)}><option value="">{text.allTypes} · {tasks.length}</option>{types.map((value) => <option key={value} value={value}>{text.types[value] || value} · {tasks.filter((task) => task.task_type === value).length}</option>)}</select></th><th className="state-column"><select className="table-filter-select" aria-label={text.state} value={state} onChange={(event) => setState(event.target.value as "" | "active" | "attention" | TaskState)}><option value="">{text.allStates} · {stats.total}</option><option value="active">{text.active} · {stats.active}</option><option value="attention">{text.attention} · {stats.attention}</option>{Object.entries(text.states).map(([key, label]) => <option key={key} value={key}>{label} · {tasks.filter((task) => task.state === key).length}</option>)}</select></th><th className="progress-column">{text.progress}</th><th className="started-column">{text.started}</th><th className="duration-column">{text.duration}</th><th className="action-column">{selected.size > 0 ? <button className="danger-outline bulk-delete" onClick={() => setDeleteOpen(true)}><Trash2 size={14} />{selected.size}</button> : text.action}</th></tr></thead>
          <tbody>{filtered.map((task) => <TaskRow key={task.task_id} task={task} language={language} selected={selected.has(task.task_id)} onSelect={() => toggleTask(task.task_id)} onOpen={() => onOpenTask(task.task_id)} onCancel={() => setCancelTarget(task)} />)}</tbody>
        </table>
        {!loading && filtered.length === 0 && <div className="empty-state"><span className="empty-glyph">⌁</span><strong>{tasks.length ? text.noMatches : text.noTasks}</strong><p>{tasks.length ? text.noMatches : text.noTasksHint}</p>{!tasks.length && <button className="primary-button" onClick={onSubmit}><Plus size={17} />{text.pages.submit}</button>}</div>}
        {loading && <div className="loading-state"><LoaderCircle className="spin" /> Loading AxonX runtime…</div>}
      </div>
    </div>
    {cancelTarget && <div className="modal-backdrop" onMouseDown={() => setCancelTarget(null)}><div className="confirm-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true"><button className="close-button" onClick={() => setCancelTarget(null)}><X /></button><span className="danger-icon"><Ban /></span><h2>{text.cancelConfirm}</h2><code>{cancelTarget.task_id}</code><div><button className="secondary-button" onClick={() => setCancelTarget(null)}>{text.close}</button><button className="danger-button" onClick={() => void confirmCancel()} disabled={cancelling}>{cancelling ? text.cancelling : text.confirmCancel}</button></div></div></div>}
    {deleteOpen && <div className="modal-backdrop" onMouseDown={() => setDeleteOpen(false)}><div className="confirm-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true"><button className="close-button" onClick={() => setDeleteOpen(false)}><X /></button><span className="danger-icon"><Trash2 /></span><h2>{interpolate(text.deleteConfirm, { count: selected.size })}</h2><p>{text.deleteHint}</p><div><button className="secondary-button" onClick={() => setDeleteOpen(false)}>{text.close}</button><button className="danger-button" onClick={() => void confirmDelete()} disabled={deleting}>{deleting ? text.deleting : text.confirmDelete}</button></div></div></div>}
  </section>;
}

function taskTimestamp(task: TaskStatus) {
  const value = task.started_at || task.finished_at;
  if (value) return new Date(value).getTime();
  const compact = task.task_id.split("#")[1];
  if (!/^\d{14}$/.test(compact || "")) return 0;
  const iso = `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}T${compact.slice(8, 10)}:${compact.slice(10, 12)}:${compact.slice(12, 14)}Z`;
  return new Date(iso).getTime();
}

function TaskRow({ task, language, selected, onSelect, onOpen, onCancel }: { task: TaskStatus; language: Language; selected: boolean; onSelect: () => void; onOpen: () => void; onCancel: () => void }) {
  const text = t(language); const progress = taskStepProgress(task);
  const selectable = !ACTIVE.has(task.state);
  const [copied, setCopied] = useState(false);
  const copyTaskId = async () => {
    await navigator.clipboard.writeText(task.task_id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  return <tr className={selected ? "selected" : ""} onClick={onOpen}><td className="select-column" onClick={(event) => event.stopPropagation()}><input type="checkbox" aria-label={interpolate(text.selectTask, { taskId: task.task_id })} checked={selected} disabled={!selectable} onChange={onSelect} /></td><td className="task-id-column"><div className="task-identity"><span className={`task-orb ${task.state}`}>{task.task_type.slice(0, 1).toUpperCase()}</span><div><span className="task-id-line"><strong title={task.task_id}>{task.task_id}</strong><button type="button" className={copied ? "copied" : ""} aria-label={copied ? text.copied : text.copyTaskId} title={copied ? text.copied : text.copyTaskId} onClick={(event) => { event.stopPropagation(); void copyTaskId(); }}>{copied ? <><Check /><span aria-live="polite">{text.copied}</span></> : <Copy />}</button></span><small>PID {task.pid || "—"}</small></div></div></td><td className="type-column"><span className="type-chip">{text.types[task.task_type] || task.task_type}</span></td><td className="state-column"><Status state={task.state} language={language} /></td><td className="progress-column">{progress ? <div className="progress-cell"><span className="progress-step"><small>{text.step}</small><strong>{progress.current}</strong></span><span className="progress-ring" style={{ "--step-progress": `${progress.percentage}%` } as React.CSSProperties}><strong>{progress.percentage}</strong><small>%</small></span></div> : <span className="muted">{text.notStarted}</span>}</td><td className="started-column">{formatDate(task.started_at, language)}</td><td className="duration-column">{formatDuration(task, language)}</td><td className="action-column"><div className="row-actions">{ACTIVE.has(task.state) && <button className="text-danger" onClick={(event) => { event.stopPropagation(); onCancel(); }}>{text.cancel}</button>}<button aria-label={text.details}><ChevronRight /></button></div></td></tr>;
}

export function Status({ state, language }: { state: TaskState; language: Language }) { return <span className={`status-badge ${state}`}><i />{t(language).states[state]}</span>; }
