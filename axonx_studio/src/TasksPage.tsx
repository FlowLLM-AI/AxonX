import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowUpRight, Ban, CheckCircle2, ChevronRight, Clock3, LoaderCircle, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { cancelTask, deleteTasks, listTaskStatuses } from "./api";
import { interpolate, t } from "./i18n";
import { formatDate, formatDuration, taskStepProgress } from "./taskFormat";
import type { Language, TaskState, TaskStatus } from "./types";

const ACTIVE = new Set<TaskState>(["queued", "running"]);
const ATTENTION = new Set<TaskState>(["failed", "cancelled"]);

export function TasksPage({ language, remoteIp, onSubmit, onOpenTask, onConnection }: { language: Language; remoteIp?: string; onSubmit: () => void; onOpenTask: (taskId: string) => void; onConnection: (online: boolean) => void }) {
  const text = t(language);
  const [tasks, setTasks] = useState<TaskStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [seconds, setSeconds] = useState(10);
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
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
    return matches && (!state || task.state === state) && (!type || task.task_type === type);
  }), [tasks, search, state, type]);
  const stats = {
    total: tasks.length,
    active: tasks.filter((item) => ACTIVE.has(item.state)).length,
    succeeded: tasks.filter((item) => item.state === "succeeded").length,
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

    <div className="stats-grid">
      <Stat label={text.total} value={stats.total} tone="blue" icon={<Clock3 />} />
      <Stat label={text.active} value={stats.active} tone="cyan" icon={<LoaderCircle />} live />
      <Stat label={text.succeeded} value={stats.succeeded} tone="green" icon={<CheckCircle2 />} />
      <Stat label={text.attention} value={stats.attention} tone="amber" icon={<AlertTriangle />} />
    </div>

    {error && <div className="error-banner"><AlertTriangle size={18} /><div><strong>{text.requestFailed}</strong><span>{error} · {text.staleHint}</span></div><button onClick={() => void load()}>{text.retry}</button></div>}

    <div className="data-panel">
      <div className="filter-bar">
        <label className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={text.search} /></label>
        <select value={state} onChange={(event) => setState(event.target.value)}><option value="">{text.allStates}</option>{Object.entries(text.states).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
        <select value={type} onChange={(event) => setType(event.target.value)}><option value="">{text.allTypes}</option>{types.map((value) => <option key={value} value={value}>{text.types[value] || value}</option>)}</select>
        {selected.size > 0 && <button className="danger-outline bulk-delete" onClick={() => setDeleteOpen(true)}><Trash2 size={15} />{interpolate(text.deleteSelected, { count: selected.size })}</button>}
        <span className="result-count">{filtered.length} / {tasks.length}</span>
      </div>
      <div className="table-wrap">
        <table><thead><tr><th className="select-column"><input type="checkbox" aria-label={text.selectAll} checked={allVisibleSelected} disabled={!selectableIds.length} onChange={toggleAllVisible} /></th><th>{text.taskId}</th><th>{text.type}</th><th>{text.state}</th><th>{text.progress}</th><th>{text.started}</th><th>{text.duration}</th><th>{text.action}</th></tr></thead>
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

function Stat({ label, value, tone, icon, live }: { label: string; value: number; tone: string; icon: React.ReactNode; live?: boolean }) {
  return <article className={`stat-card ${tone}`}><div className="stat-icon">{icon}</div><span>{label}</span><strong>{value.toLocaleString()}</strong>{live && value > 0 ? <i className="pulse-dot" /> : <ArrowUpRight className="stat-arrow" />}</article>;
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
  return <tr className={selected ? "selected" : ""} onClick={onOpen}><td className="select-column" onClick={(event) => event.stopPropagation()}><input type="checkbox" aria-label={interpolate(text.selectTask, { taskId: task.task_id })} checked={selected} disabled={!selectable} onChange={onSelect} /></td><td><div className="task-identity"><span className={`task-orb ${task.state}`}>{task.task_type.slice(0, 1).toUpperCase()}</span><div><strong>{task.task_id}</strong><small>PID {task.pid || "—"}</small></div></div></td><td><span className="type-chip">{text.types[task.task_type] || task.task_type}</span></td><td><Status state={task.state} language={language} /></td><td>{progress ? <div className="progress-cell"><div className="progress-label"><strong>{text.step} {progress.current}</strong><code title={progress.name}>{progress.name}</code><span>{progress.percentage}%</span></div><div className="progress-track"><i style={{ width: `${progress.percentage}%` }} /></div></div> : <span className="muted">{text.notStarted}</span>}</td><td>{formatDate(task.started_at, language)}</td><td>{formatDuration(task, language)}</td><td><div className="row-actions">{ACTIVE.has(task.state) && <button className="text-danger" onClick={(event) => { event.stopPropagation(); onCancel(); }}>{text.cancel}</button>}<button aria-label={text.details}><ChevronRight /></button></div></td></tr>;
}

export function Status({ state, language }: { state: TaskState; language: Language }) { return <span className={`status-badge ${state}`}><i />{t(language).states[state]}</span>; }
