import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Ban, ChevronUp, Copy, FileText, LoaderCircle, RefreshCw } from "lucide-react";
import { cancelTask, getTaskStatus, readTaskLog } from "./api";
import { t } from "./i18n";
import { Status } from "./TasksPage";
import { formatDate, formatDuration, taskStepProgress } from "./taskFormat";
import type { Language, TaskStatus } from "./types";

const ACTIVE = new Set(["queued", "running"]);
const LOG_CHUNK_BYTES = 65_536;
const MAX_LOG_CHARACTERS = 524_288;

export function TaskDetailPage({ taskId, language, remoteIp, onBack, onConnection }: { taskId: string; language: Language; remoteIp?: string; onBack: () => void; onConnection: (online: boolean) => void }) {
  const text = t(language);
  const labels = language === "zh" ? {
    live: "实时日志", loadEarlier: "加载更早日志", follow: "跟随末尾", copy: "复制", copied: "已复制",
    logEmpty: "日志暂时为空", logUnavailable: "该任务没有可读取的日志", logError: "日志读取失败",
    loaded: "已加载", of: "/", bounded: "浏览器最多保留约 512 KB，较早内容会自动丢弃。",
    back: "返回任务列表", refreshing: "刷新中", taskMissing: "无法读取任务详情",
  } : {
    live: "Live log", loadEarlier: "Load earlier", follow: "Follow tail", copy: "Copy", copied: "Copied",
    logEmpty: "The log is empty for now", logUnavailable: "No readable log is attached to this task", logError: "Unable to read log",
    loaded: "Loaded", of: "/", bounded: "The browser keeps about 512 KB; older content is discarded automatically.",
    back: "Back to task runs", refreshing: "Refreshing", taskMissing: "Unable to load task details",
  };
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const [logText, setLogText] = useState("");
  const [logError, setLogError] = useState("");
  const [logLoading, setLogLoading] = useState(false);
  const [startOffset, setStartOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState(0);
  const [fileSize, setFileSize] = useState(0);
  const [hasEarlier, setHasEarlier] = useState(false);
  const [trimmed, setTrimmed] = useState(false);
  const [followTail, setFollowTail] = useState(true);
  const [copied, setCopied] = useState(false);
  const logViewport = useRef<HTMLPreElement>(null);
  const logRequest = useRef(false);
  const logLength = useRef(0);

  const loadStatus = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true); else setLoading(true);
    try {
      const result = await getTaskStatus(taskId, remoteIp);
      setTask(result); setError(""); onConnection(true);
      return result;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false);
      return null;
    } finally { setLoading(false); setRefreshing(false); }
  }, [onConnection, remoteIp, taskId]);

  const loadLog = useCallback(async (offset: number, mode: "replace" | "append" | "prepend") => {
    if (logRequest.current) return;
    logRequest.current = true; setLogLoading(true);
    try {
      const limit = mode === "prepend" ? Math.min(LOG_CHUNK_BYTES, Math.max(1024, MAX_LOG_CHARACTERS - logLength.current)) : LOG_CHUNK_BYTES;
      const chunk = await readTaskLog(taskId, offset, limit, remoteIp);
      setFileSize(chunk.file_size); setLogError("");
      if (mode === "replace" || chunk.reset) {
        logLength.current = chunk.content.length;
        setLogText(chunk.content); setStartOffset(chunk.start_offset); setTrimmed(false); setNextOffset(chunk.next_offset); setHasEarlier(chunk.has_more_before);
      } else if (mode === "prepend") {
        setLogText((current) => { const combined = `${chunk.content}${current}`; logLength.current = combined.length; return combined; });
        setStartOffset(chunk.start_offset); setHasEarlier(chunk.has_more_before);
      } else if (chunk.content) {
        setLogText((current) => {
          const combined = `${current}${chunk.content}`;
          if (combined.length <= MAX_LOG_CHARACTERS) { logLength.current = combined.length; return combined; }
          logLength.current = MAX_LOG_CHARACTERS;
          setTrimmed(true); setHasEarlier(false); return combined.slice(-MAX_LOG_CHARACTERS);
        });
        setNextOffset(chunk.next_offset);
      }
    } catch (reason) {
      setLogError(reason instanceof Error ? reason.message : String(reason));
    } finally { logRequest.current = false; setLogLoading(false); }
  }, [remoteIp, taskId]);

  useEffect(() => { void loadStatus().then((result) => { if (result?.log_path) void loadLog(-1, "replace"); }); }, [loadLog, loadStatus]);
  useEffect(() => {
    if (!task || !ACTIVE.has(task.state)) return;
    const timer = window.setInterval(() => {
      void loadStatus(true);
      if (task.log_path) void loadLog(nextOffset, "append");
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [loadLog, loadStatus, nextOffset, task]);
  useEffect(() => {
    if (followTail && logViewport.current) logViewport.current.scrollTop = logViewport.current.scrollHeight;
  }, [followTail, logText]);

  const refresh = async () => {
    const result = await loadStatus(true);
    if (result?.log_path) await loadLog(-1, "replace");
  };
  const copyLog = async () => {
    await navigator.clipboard.writeText(logText); setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  };
  const cancel = async () => {
    if (!task || !window.confirm(text.cancelConfirm)) return;
    setCancelling(true);
    try {
      const cancelled = await cancelTask(task.task_id, remoteIp);
      if (!cancelled) throw new Error(text.cancelFailed);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCancelling(false);
    }
  };

  if (loading && !task) return <section className="workspace-page task-detail-loading"><LoaderCircle className="spin" />{labels.refreshing}</section>;
  if (!task) return <section className="workspace-page"><button className="detail-back" onClick={onBack}><ArrowLeft />{labels.back}</button><div className="error-banner"><strong>{labels.taskMissing}</strong><span>{error}</span></div></section>;
  const progress = taskStepProgress(task);

  return <section className="workspace-page task-detail-page">
    <div className="task-detail-heading">
      <button className="detail-back" onClick={onBack}><ArrowLeft />{labels.back}</button>
      <div><p className="eyebrow">TASK RUN / DETAIL</p><h1>{task.task_id}</h1><span>{text.types[task.task_type] || task.task_type} · PID {task.pid || "—"}</span></div>
      <div className="heading-actions"><button className="secondary-button" onClick={() => void refresh()} disabled={refreshing}><RefreshCw className={refreshing ? "spin" : ""} />{text.refreshNow}</button>{ACTIVE.has(task.state) && <button className="danger-outline" onClick={() => void cancel()} disabled={cancelling}><Ban />{cancelling ? text.cancelling : text.cancel}</button>}</div>
    </div>
    {error && <div className="error-banner"><strong>{text.requestFailed}</strong><span>{error}</span></div>}
    <div className="task-detail-layout">
      <div className="task-detail-summary">
        <div className="drawer-status"><span className={`task-orb ${task.state}`}>{task.task_type.slice(0, 1).toUpperCase()}</span><div><Status state={task.state} language={language} /><p>{text.types[task.task_type] || task.task_type}</p></div></div>
        <section className="detail-grid"><div><small>{text.started}</small><strong>{formatDate(task.started_at, language)}</strong></div><div><small>{text.duration}</small><strong>{formatDuration(task, language)}</strong></div><div><small>EXIT CODE</small><strong>{task.exit_code}</strong></div><div><small>{text.progress}</small>{progress ? <strong className="detail-step-progress"><span>{text.step} {progress.current}</span><code title={progress.name}>{progress.name}</code><em>{progress.percentage}%</em></strong> : <strong>{text.notStarted}</strong>}</div></section>
        <DetailSection title={text.steps}><div className="step-list">{task.steps.length ? task.steps.map((step, index) => {
          const percentage = Math.max(0, Math.min(100, step.percentage ?? 0));
          return <div className="step-item" key={`${step.name}-${index}`}><span className={step.finished_at ? "done" : "active"} style={step.finished_at ? undefined : { "--step-progress": `${percentage}%` } as React.CSSProperties}>{step.finished_at ? "✓" : index + 1}</span><div><strong>{step.name}</strong><small>{step.finished_at ? formatDate(step.finished_at, language) : step.started_at ? `${Math.round(percentage)}%` : text.notStarted}</small></div></div>;
        }) : <p className="muted">{text.notStarted}</p>}</div></DetailSection>
        {task.error && <DetailSection title={text.error}><pre className="error-code">{task.error}</pre></DetailSection>}
        <DetailSection title={text.result}><pre>{Object.keys(task.result).length ? JSON.stringify(task.result, null, 2) : text.noResult}</pre></DetailSection>
      </div>
      <section className="log-panel">
        <header><div><span className="log-title"><FileText />{labels.live}{ACTIVE.has(task.state) && <i />}</span><code title={task.log_path}>{task.log_path || labels.logUnavailable}</code></div><div><label className="log-follow"><input type="checkbox" checked={followTail} onChange={(event) => setFollowTail(event.target.checked)} />{labels.follow}</label><button onClick={() => void copyLog()} disabled={!logText}><Copy />{copied ? labels.copied : labels.copy}</button></div></header>
        <div className="log-meta"><span>{labels.loaded} {formatBytes(Math.min(fileSize, Math.max(0, nextOffset - startOffset)))} {labels.of} {formatBytes(fileSize)}</span><span>{labels.bounded}</span></div>
        {hasEarlier && !trimmed && <button className="load-earlier" onClick={() => void loadLog(Math.max(0, startOffset - LOG_CHUNK_BYTES), "prepend")} disabled={logLoading || logText.length > MAX_LOG_CHARACTERS - 1024}><ChevronUp />{labels.loadEarlier}</button>}
        {logError ? <div className="log-placeholder error"><strong>{labels.logError}</strong><span>{logError}</span></div> : !task.log_path ? <div className="log-placeholder">{labels.logUnavailable}</div> : !logText && !logLoading ? <div className="log-placeholder">{labels.logEmpty}</div> : <pre className="log-content" ref={logViewport}>{logText}{logLoading && <span className="log-cursor" />}</pre>}
      </section>
    </div>
  </section>;
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) { return <section className="detail-section"><h3>{title}</h3>{children}</section>; }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 ** 2).toFixed(1)} MB`; }
