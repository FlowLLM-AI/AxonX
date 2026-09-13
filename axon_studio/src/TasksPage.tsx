import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowUpRight, Ban, CheckCircle2, ChevronRight, Clock3, LoaderCircle, Plus, RefreshCw, Search, X } from "lucide-react";
import { cancelTask, listTaskStatuses } from "./api";
import { interpolate, t } from "./i18n";
import type { Language, TaskState, TaskStatus } from "./types";

const ACTIVE = new Set<TaskState>(["queued", "running"]);
const ATTENTION = new Set<TaskState>(["failed", "cancelled"]);

export function TasksPage({ language, onSubmit, onConnection }: { language: Language; onSubmit: () => void; onConnection: (online: boolean) => void }) {
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
  const [selected, setSelected] = useState<TaskStatus | null>(null);
  const [cancelTarget, setCancelTarget] = useState<TaskStatus | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await listTaskStatuses();
      const ordered = [...result].sort((left, right) => taskTimestamp(right) - taskTimestamp(left));
      setTasks(ordered);
      setSelected((current) => current ? ordered.find((item) => item.task_id === current.task_id) || current : null);
      setError(""); onConnection(true); setSeconds(10);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false);
    } finally { setLoading(false); setRefreshing(false); }
  }, [onConnection]);

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

  const confirmCancel = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try { await cancelTask(cancelTarget.task_id); setCancelTarget(null); await load(true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setCancelling(false); }
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
        <span className="result-count">{filtered.length} / {tasks.length}</span>
      </div>
      <div className="table-wrap">
        <table><thead><tr><th>{text.taskId}</th><th>{text.type}</th><th>{text.state}</th><th>{text.progress}</th><th>{text.started}</th><th>{text.duration}</th><th>{text.action}</th></tr></thead>
          <tbody>{filtered.map((task) => <TaskRow key={task.task_id} task={task} language={language} onOpen={() => setSelected(task)} onCancel={() => setCancelTarget(task)} />)}</tbody>
        </table>
        {!loading && filtered.length === 0 && <div className="empty-state"><span className="empty-glyph">⌁</span><strong>{tasks.length ? text.noMatches : text.noTasks}</strong><p>{tasks.length ? text.noMatches : text.noTasksHint}</p>{!tasks.length && <button className="primary-button" onClick={onSubmit}><Plus size={17} />{text.pages.submit}</button>}</div>}
        {loading && <div className="loading-state"><LoaderCircle className="spin" /> Loading AxonX runtime…</div>}
      </div>
    </div>
    {selected && <TaskDrawer task={selected} language={language} onClose={() => setSelected(null)} onCancel={() => setCancelTarget(selected)} />}
    {cancelTarget && <div className="modal-backdrop" onMouseDown={() => setCancelTarget(null)}><div className="confirm-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog" aria-modal="true"><button className="close-button" onClick={() => setCancelTarget(null)}><X /></button><span className="danger-icon"><Ban /></span><h2>{text.cancelConfirm}</h2><code>{cancelTarget.task_id}</code><div><button className="secondary-button" onClick={() => setCancelTarget(null)}>{text.close}</button><button className="danger-button" onClick={() => void confirmCancel()} disabled={cancelling}>{cancelling ? text.cancelling : text.confirmCancel}</button></div></div></div>}
  </section>;
}

function Stat({ label, value, tone, icon, live }: { label: string; value: number; tone: string; icon: React.ReactNode; live?: boolean }) {
  return <article className={`stat-card ${tone}`}><div className="stat-icon">{icon}</div><span>{label}</span><strong>{value.toLocaleString()}</strong>{live && value > 0 ? <i className="pulse-dot" /> : <ArrowUpRight className="stat-arrow" />}</article>;
}

function taskProgress(task: TaskStatus) {
  if (task.state === "succeeded") return 100;
  if (!task.steps.length) return 0;
  const completed = task.steps.filter((step) => step.finished_at).length;
  const current = task.steps.find((step) => !step.finished_at)?.percentage || 0;
  return Math.min(100, Math.round(((completed + current / 100) / task.steps.length) * 100));
}

function taskTimestamp(task: TaskStatus) {
  const value = task.started_at || task.finished_at;
  if (value) return new Date(value).getTime();
  const compact = task.task_id.split("#")[1];
  if (!/^\d{14}$/.test(compact || "")) return 0;
  const iso = `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}T${compact.slice(8, 10)}:${compact.slice(10, 12)}:${compact.slice(12, 14)}Z`;
  return new Date(iso).getTime();
}

function TaskRow({ task, language, onOpen, onCancel }: { task: TaskStatus; language: Language; onOpen: () => void; onCancel: () => void }) {
  const text = t(language); const progress = taskProgress(task);
  return <tr onClick={onOpen}><td><div className="task-identity"><span className={`task-orb ${task.state}`}>{task.task_type.slice(0, 1).toUpperCase()}</span><div><strong>{task.task_id}</strong><small>PID {task.pid || "—"}</small></div></div></td><td><span className="type-chip">{text.types[task.task_type] || task.task_type}</span></td><td><Status state={task.state} language={language} /></td><td><div className="progress-cell"><div><i style={{ width: `${progress}%` }} /></div><span>{progress}%</span></div></td><td>{formatDate(task.started_at, language)}</td><td>{formatDuration(task, language)}</td><td><div className="row-actions">{ACTIVE.has(task.state) && <button className="text-danger" onClick={(event) => { event.stopPropagation(); onCancel(); }}>{text.cancel}</button>}<button aria-label={text.details}><ChevronRight /></button></div></td></tr>;
}

function Status({ state, language }: { state: TaskState; language: Language }) { return <span className={`status-badge ${state}`}><i />{t(language).states[state]}</span>; }
function formatDate(value: string | null, language: Language) { return value ? new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en-US", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value)) : "—"; }
function formatDuration(task: TaskStatus, language: Language) {
  if (!task.started_at) return "—";
  const end = task.finished_at ? new Date(task.finished_at).getTime() : Date.now();
  const seconds = Math.max(0, Math.floor((end - new Date(task.started_at).getTime()) / 1000));
  if (language === "zh") {
    if (seconds < 60) return `${seconds} 秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
    return `${Math.floor(seconds / 3600)} 小时 ${Math.floor(seconds % 3600 / 60)} 分`;
  }
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m`;
}

function TaskDrawer({ task, language, onClose, onCancel }: { task: TaskStatus; language: Language; onClose: () => void; onCancel: () => void }) {
  const text = t(language);
  return <div className="drawer-backdrop" onMouseDown={onClose}><aside className="task-drawer" onMouseDown={(event) => event.stopPropagation()}><header><div><p>{text.taskDetails}</p><h2>{task.task_id}</h2></div><button className="close-button" onClick={onClose}><X /></button></header><div className="drawer-body"><div className="drawer-status"><span className={`task-orb ${task.state}`}>{task.task_type.slice(0, 1).toUpperCase()}</span><div><Status state={task.state} language={language} /><p>{text.types[task.task_type] || task.task_type} · PID {task.pid || "—"}</p></div>{ACTIVE.has(task.state) && <button className="danger-outline" onClick={onCancel}><Ban size={15} />{text.cancel}</button>}</div><section className="detail-grid"><div><small>{text.started}</small><strong>{formatDate(task.started_at, language)}</strong></div><div><small>{text.duration}</small><strong>{formatDuration(task, language)}</strong></div><div><small>EXIT CODE</small><strong>{task.exit_code}</strong></div><div><small>{text.progress}</small><strong>{taskProgress(task)}%</strong></div></section><DetailSection title={text.steps}><div className="step-list">{task.steps.length ? task.steps.map((step, index) => <div className="step-item" key={`${step.name}-${index}`}><span className={step.finished_at ? "done" : "active"}>{step.finished_at ? "✓" : index + 1}</span><div><strong>{step.name}</strong><small>{step.finished_at ? formatDate(step.finished_at, language) : step.started_at ? `${Math.round(step.percentage || 0)}%` : text.notStarted}</small></div></div>) : <p className="muted">{text.notStarted}</p>}</div></DetailSection>{task.error && <DetailSection title={text.error}><pre className="error-code">{task.error}</pre></DetailSection>}<DetailSection title={text.result}><pre>{Object.keys(task.result).length ? JSON.stringify(task.result, null, 2) : text.noResult}</pre></DetailSection>{task.log_path && <DetailSection title={text.logPath}><code className="path-code">{task.log_path}</code></DetailSection>}</div></aside></div>;
}
function DetailSection({ title, children }: { title: string; children: React.ReactNode }) { return <section className="detail-section"><h3>{title}</h3>{children}</section>; }
