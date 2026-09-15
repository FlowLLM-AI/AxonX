import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Ban, Check, ChevronUp, Copy, FileJson, FileText, LoaderCircle, Play, RefreshCw, RotateCw, Settings2, X } from "lucide-react";
import { cancelTask, getTaskStatus, readTaskLog, submitTask } from "./api";
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
    config: "任务配置", effectiveConfig: "本次实际执行的配置快照", configUnavailable: "旧运行未保存配置快照",
    noConfig: "本任务没有额外配置参数", copyConfig: "复制配置", rerun: "重新运行", rerunning: "正在提交",
    rerunConfirm: "使用本次配置重新运行任务？", rerunHint: "系统会创建一条新的运行记录，不会覆盖当前记录。",
    confirmRerun: "确认重跑", rerunSubmitted: "已提交新的任务运行", rerunFailed: "重新运行失败",
    runDetails: "运行详情", completedSteps: "个步骤已完成", unavailableRerun: "该运行缺少可重用的任务名称",
  } : {
    live: "Live log", loadEarlier: "Load earlier", follow: "Follow tail", copy: "Copy", copied: "Copied",
    logEmpty: "The log is empty for now", logUnavailable: "No readable log is attached to this task", logError: "Unable to read log",
    loaded: "Loaded", of: "/", bounded: "The browser keeps about 512 KB; older content is discarded automatically.",
    back: "Back to task runs", refreshing: "Refreshing", taskMissing: "Unable to load task details",
    config: "Task configuration", effectiveConfig: "Effective configuration snapshot for this run", configUnavailable: "No configuration snapshot was saved for this legacy run",
    noConfig: "This task has no additional configuration", copyConfig: "Copy config", rerun: "Run again", rerunning: "Submitting",
    rerunConfirm: "Run this task again with the same configuration?", rerunHint: "A new run will be created; this record will not be changed.",
    confirmRerun: "Run again", rerunSubmitted: "A new task run was submitted", rerunFailed: "Unable to rerun task",
    runDetails: "Run details", completedSteps: "steps completed", unavailableRerun: "This run does not include a reusable task name",
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
  const [configCopied, setConfigCopied] = useState(false);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [rerunMessage, setRerunMessage] = useState("");
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
  const copyConfig = async () => {
    if (!task) return;
    await navigator.clipboard.writeText(JSON.stringify(task.config || {}, null, 2));
    setConfigCopied(true);
    window.setTimeout(() => setConfigCopied(false), 1_500);
  };
  const rerun = async () => {
    if (!task?.task_name) return;
    setRerunning(true); setRerunMessage("");
    try {
      await submitTask(task.task_name, task.config || {}, remoteIp);
      setRerunOpen(false); setRerunMessage(labels.rerunSubmitted); onConnection(true);
    } catch (reason) {
      setRerunMessage(`${labels.rerunFailed}: ${reason instanceof Error ? reason.message : String(reason)}`);
      onConnection(false);
    } finally {
      setRerunning(false);
    }
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
  const configEntries = Object.entries(task.config || {});
  const canRerun = Boolean(task.task_name);
  const completedSteps = task.steps.filter((step) => step.percentage === 100).length;

  return <section className="workspace-page task-detail-page">
    <div className="task-detail-heading">
      <button className="detail-back" onClick={onBack}><ArrowLeft />{labels.back}</button>
      <div><p className="eyebrow">TASK RUN / DETAIL</p><h1>{task.task_id}</h1><span>{text.types[task.task_type] || task.task_type} · PID {task.pid || "—"}</span></div>
      <div className="heading-actions">
        <button className="secondary-button" onClick={() => void refresh()} disabled={refreshing}><RefreshCw className={refreshing ? "spin" : ""} />{text.refreshNow}</button>
        {ACTIVE.has(task.state)
          ? <button className="danger-outline" onClick={() => void cancel()} disabled={cancelling}><Ban />{cancelling ? text.cancelling : text.cancel}</button>
          : <button className="primary-button task-rerun-button" onClick={() => setRerunOpen(true)} disabled={!canRerun || rerunning} title={canRerun ? labels.rerun : labels.unavailableRerun}><RotateCw />{labels.rerun}</button>}
      </div>
    </div>
    {error && <div className="error-banner"><strong>{text.requestFailed}</strong><span>{error}</span></div>}
    {rerunMessage && <div className={`task-rerun-notice ${rerunMessage.startsWith(labels.rerunFailed) ? "error" : ""}`}><Play />{rerunMessage}</div>}
    <div className="task-detail-layout">
      <div className="task-detail-summary">
        <section className="task-config-section">
          <header className="detail-section-heading">
            <div><span className="detail-section-icon"><Settings2 /></span><div><h2>{labels.config}</h2><p>{task.task_name ? labels.effectiveConfig : labels.configUnavailable}</p></div></div>
            <button className="config-copy-button" onClick={() => void copyConfig()} disabled={!task.task_name}><Copy />{configCopied ? labels.copied : labels.copyConfig}</button>
          </header>
          {task.task_name ? <>
            <div className="config-source"><span>{language === "zh" ? "任务" : "Task"}</span><code>{task.task_name}</code><i>{language === "zh" ? "完整快照" : "Snapshot"}</i></div>
            {configEntries.length ? <dl className="task-config-list">{configEntries.map(([key, value]) => <div key={key}><dt>{key}</dt><dd title={formatConfigValue(value)}>{formatConfigValue(value)}</dd></div>)}</dl> : <div className="task-config-empty"><FileJson />{labels.noConfig}</div>}
          </> : <div className="task-config-empty legacy"><FileJson />{labels.configUnavailable}</div>}
        </section>

        <section className="task-run-section">
          <header className="detail-section-heading run-heading">
            <div><span className={`task-orb ${task.state}`}>{task.task_type.slice(0, 1).toUpperCase()}</span><div><h2>{labels.runDetails}</h2><p><Status state={task.state} language={language} /> · {completedSteps} {labels.completedSteps}</p></div></div>
          </header>
          <div className="task-run-meta">
            <div><small>{text.started}</small><strong>{formatDate(task.started_at, language)}</strong></div>
            <div><small>{text.duration}</small><strong>{formatDuration(task, language)}</strong></div>
            <div><small>EXIT CODE</small><strong>{task.exit_code}</strong></div>
          </div>
          {progress && <div className="task-current-step"><span>{text.progress}</span><code title={progress.name}>{progress.name}</code><strong>{progress.percentage}%</strong></div>}
          <DetailSection title={text.steps}><div className="step-list">{task.steps.length ? task.steps.map((step, index) => {
          const percentage = Math.max(0, Math.min(100, step.percentage ?? 0));
          const failed = task.state === "failed" && index === task.steps.length - 1;
          const done = !failed && step.percentage === 100;
          return <div className={`step-item ${failed ? "failed" : ""}`} key={`${step.name}-${index}`}><span className={failed ? "failed" : done ? "done" : "active"} style={!failed && !done ? { "--step-progress": `${percentage}%` } as React.CSSProperties : undefined}>{failed ? <X /> : done ? <Check /> : index + 1}</span><div><strong>{step.name}</strong><small>{failed ? task.error || text.error : step.finished_at ? formatDate(step.finished_at, language) : step.started_at ? `${Math.round(percentage)}%` : text.notStarted}</small></div></div>;
        }) : <p className="muted">{text.notStarted}</p>}</div></DetailSection>
          {Object.keys(task.result).length > 0 && <DetailSection title={text.result}><pre>{JSON.stringify(task.result, null, 2)}</pre></DetailSection>}
        </section>
      </div>
      <section className="log-panel">
        <header><div><span className="log-title"><FileText />{labels.live}{ACTIVE.has(task.state) && <i />}</span><code title={task.log_path}>{task.log_path || labels.logUnavailable}</code></div><div><label className="log-follow"><input type="checkbox" checked={followTail} onChange={(event) => setFollowTail(event.target.checked)} />{labels.follow}</label><button onClick={() => void copyLog()} disabled={!logText}><Copy />{copied ? labels.copied : labels.copy}</button></div></header>
        <div className="log-meta"><span>{labels.loaded} {formatBytes(Math.min(fileSize, Math.max(0, nextOffset - startOffset)))} {labels.of} {formatBytes(fileSize)}</span><span>{labels.bounded}</span></div>
        {hasEarlier && !trimmed && <button className="load-earlier" onClick={() => void loadLog(Math.max(0, startOffset - LOG_CHUNK_BYTES), "prepend")} disabled={logLoading || logText.length > MAX_LOG_CHARACTERS - 1024}><ChevronUp />{labels.loadEarlier}</button>}
        {logError ? <div className="log-placeholder error"><strong>{labels.logError}</strong><span>{logError}</span></div> : !task.log_path ? <div className="log-placeholder">{labels.logUnavailable}</div> : !logText && !logLoading ? <div className="log-placeholder">{labels.logEmpty}</div> : <pre className="log-content" ref={logViewport}>{logText}{logLoading && <span className="log-cursor" />}</pre>}
      </section>
    </div>
    {rerunOpen && <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) setRerunOpen(false); }}>
      <section className="confirm-modal rerun-modal" role="dialog" aria-modal="true" aria-labelledby="rerun-title">
        <button className="close-button" onClick={() => setRerunOpen(false)} aria-label={text.close}><X /></button>
        <span className="rerun-icon"><RotateCw /></span>
        <h2 id="rerun-title">{labels.rerunConfirm}</h2>
        <p>{labels.rerunHint}</p>
        <div className="rerun-config-summary"><strong>{task.task_name}</strong><span>{configEntries.length} {language === "zh" ? "项配置参数" : "configuration values"}</span></div>
        <div><button className="secondary-button" onClick={() => setRerunOpen(false)}>{text.close}</button><button className="primary-button" onClick={() => void rerun()} disabled={rerunning}>{rerunning ? <LoaderCircle className="spin" /> : <RotateCw />}{rerunning ? labels.rerunning : labels.confirmRerun}</button></div>
      </section>
    </div>}
  </section>;
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) { return <section className="detail-section"><h3>{title}</h3>{children}</section>; }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 ** 2).toFixed(1)} MB`; }
function formatConfigValue(value: unknown) {
  if (typeof value === "string") return value || '""';
  return JSON.stringify(value);
}
