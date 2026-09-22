import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Ban,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  FileJson,
  FileText,
  GitBranch,
  Bot,
  LoaderCircle,
  LocateFixed,
  Settings2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatBytes } from "../../shared/lib/format";
import { isAbortError } from "../../shared/lib/errors";
import type { JobEvent } from "../../shared/api/event";
import type { TaskStatus } from "./types";
import { cancelTask, getTaskStatus, readTaskLog, streamTask } from "./api";
import { formatDate, formatDuration, taskStepProgress } from "./format";
import { Status } from "./TasksPage";
import { TaskGraphPanel } from "../task-graph/TaskGraphPage";

const ACTIVE = new Set(["queued", "running"]);
const LOG_CHUNK_BYTES = 65_536;
const MAX_LOG_CHARACTERS = 524_288;

export function TaskDetailPage({
  taskId,
  remoteIp,
  onBack,
  onOpenTask,
  onInterpretTask,
  onConnection,
}: {
  taskId: string;
  remoteIp?: string;
  onBack: () => void;
  onOpenTask: (taskId: string) => void;
  onInterpretTask: (taskId: string) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const labels = t("taskDetail", { returnObjects: true }) as Record<
    string,
    string
  >;
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [loading, setLoading] = useState(true);
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
  const [locateRequest, setLocateRequest] = useState(0);
  const [aligned, setAligned] = useState(true);
  const [panels, setPanels] = useState({
    config: false,
    relations: false,
    details: true,
    logs: true,
  });
  const logViewport = useRef<HTMLPreElement>(null);
  const logRequest = useRef(false);
  const logLength = useRef(0);
  const taskState = task?.state;

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getTaskStatus(taskId, remoteIp);
      setTask(result);
      setError("");
      onConnection(true);
      return result;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      onConnection(false);
      return null;
    } finally {
      setLoading(false);
    }
  }, [onConnection, remoteIp, taskId]);

  const loadLog = useCallback(
    async (offset: number, mode: "replace" | "append" | "prepend") => {
      if (logRequest.current) return;
      logRequest.current = true;
      setLogLoading(true);
      try {
        const limit =
          mode === "prepend"
            ? Math.min(
                LOG_CHUNK_BYTES,
                Math.max(1024, MAX_LOG_CHARACTERS - logLength.current),
              )
            : LOG_CHUNK_BYTES;
        const chunk = await readTaskLog(taskId, offset, limit, remoteIp);
        setFileSize(chunk.file_size);
        setLogError("");
        if (mode === "replace" || chunk.reset) {
          logLength.current = chunk.content.length;
          setLogText(chunk.content);
          setStartOffset(chunk.start_offset);
          setTrimmed(false);
          setNextOffset(chunk.next_offset);
          setHasEarlier(chunk.has_more_before);
        } else if (mode === "prepend") {
          setLogText((current) => {
            const combined = `${chunk.content}${current}`;
            logLength.current = combined.length;
            return combined;
          });
          setStartOffset(chunk.start_offset);
          setHasEarlier(chunk.has_more_before);
        } else if (chunk.content) {
          setLogText((current) => {
            const combined = `${current}${chunk.content}`;
            if (combined.length <= MAX_LOG_CHARACTERS) {
              logLength.current = combined.length;
              return combined;
            }
            logLength.current = MAX_LOG_CHARACTERS;
            setTrimmed(true);
            setHasEarlier(false);
            return combined.slice(-MAX_LOG_CHARACTERS);
          });
          setNextOffset(chunk.next_offset);
        }
      } catch (reason) {
        setLogError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        logRequest.current = false;
        setLogLoading(false);
      }
    },
    [remoteIp, taskId],
  );

  useEffect(() => {
    void loadStatus().then((result) => {
      if (result?.log_path && !ACTIVE.has(result.state))
        void loadLog(-1, "replace");
    });
  }, [loadLog, loadStatus]);
  useEffect(() => {
    setPanels({
      config: false,
      relations: false,
      details: true,
      logs: true,
    });
    setAligned(true);
  }, [taskId]);
  useEffect(() => {
    if (!taskState || !ACTIVE.has(taskState)) return;
    const controller = new AbortController();
    const onEvent = (event: JobEvent<TaskStatus>) => {
      if (event.kind === "progress") {
        setTask((current) => {
          if (!current) return current;
          const step = {
            name: event.name,
            started_at: event.started_at,
            finished_at: event.finished_at,
            percentage: event.percentage,
          };
          const index = current.steps.findIndex(
            (item) => item.name === event.name,
          );
          const steps = [...current.steps];
          if (index < 0) steps.push(step);
          else steps[index] = step;
          return { ...current, steps };
        });
      }
      if (event.kind === "log") {
        setFileSize(event.file_size);
        setStartOffset(event.start_offset);
        setNextOffset(event.next_offset);
        setHasEarlier(event.has_more_before);
        setLogText((current) => {
          const combined = event.reset
            ? event.content
            : current + event.content;
          if (combined.length <= MAX_LOG_CHARACTERS) {
            logLength.current = combined.length;
            return combined;
          }
          setTrimmed(true);
          setHasEarlier(false);
          logLength.current = MAX_LOG_CHARACTERS;
          return combined.slice(-MAX_LOG_CHARACTERS);
        });
      }
    };
    void streamTask(taskId, remoteIp, controller.signal, onEvent)
      .then((result) => {
        setTask(result);
        setError("");
        onConnection(true);
      })
      .catch((reason) => {
        if (isAbortError(reason)) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        void loadStatus();
      });
    return () => controller.abort();
  }, [loadStatus, onConnection, remoteIp, taskId, taskState]);
  useEffect(() => {
    if (followTail && logViewport.current)
      logViewport.current.scrollTop = logViewport.current.scrollHeight;
  }, [followTail, logText]);

  const copyLog = async () => {
    await navigator.clipboard.writeText(logText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  };
  const copyConfig = async () => {
    if (!task) return;
    await navigator.clipboard.writeText(
      JSON.stringify(task.config || {}, null, 2),
    );
    setConfigCopied(true);
    window.setTimeout(() => setConfigCopied(false), 1_500);
  };
  const cancel = async () => {
    if (!task || !window.confirm(t("cancelConfirm"))) return;
    setCancelling(true);
    try {
      const cancelled = await cancelTask(task.task_id, remoteIp);
      if (!cancelled) throw new Error(t("cancelFailed"));
      await loadStatus();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCancelling(false);
    }
  };

  if (loading && !task)
    return (
      <section className="workspace-page task-detail-loading">
        <LoaderCircle className="spin" />
        {labels.refreshing}
      </section>
    );
  if (!task)
    return (
      <section className="workspace-page">
        <button className="detail-back" onClick={onBack}>
          <ArrowLeft />
          {labels.back}
        </button>
        <div className="error-banner">
          <strong>{labels.taskMissing}</strong>
          <span>{error}</span>
        </div>
      </section>
    );
  const progress = taskStepProgress(task);
  const configEntries = Object.entries(task.config || {});
  const completedSteps = task.steps.filter(
    (step) => step.percentage === 100,
  ).length;
  const togglePanel = (panel: keyof typeof panels) => {
    setAligned(false);
    setPanels((current) => ({ ...current, [panel]: !current[panel] }));
  };
  const locateCurrentTask = () => {
    setAligned(false);
    setPanels((current) => ({ ...current, relations: true }));
    setLocateRequest((current) => current + 1);
  };

  return (
    <section className="workspace-page task-detail-page">
      <div className="task-detail-heading">
        <button className="detail-back" onClick={onBack}>
          <ArrowLeft />
          {labels.back}
        </button>
        <div>
          <p className="eyebrow">TASK RUN / DETAIL</p>
          <h1>{task.task_id}</h1>
          <span className="task-detail-subtitle">
            <Status state={task.state} />
            {t(`types.${task.task_type}`, task.task_type)} · PID{" "}
            {task.pid || "—"}
          </span>
        </div>
        <div className="task-detail-heading-actions">
          <button
            className="secondary-button"
            onClick={() => onInterpretTask(task.task_id)}
          >
            <Bot />
            {t("agent.interpretTask")}
          </button>
          {ACTIVE.has(task.state) && (
            <button
              className="danger-outline task-detail-cancel"
              onClick={() => void cancel()}
              disabled={cancelling}
            >
              <Ban />
              {cancelling ? t("cancelling") : t("cancel")}
            </button>
          )}
        </div>
      </div>
      {error && (
        <div className="error-banner">
          <strong>{t("requestFailed")}</strong>
          <span>{error}</span>
          <button onClick={() => void loadStatus()}>{t("retry")}</button>
        </div>
      )}
      <div
        className={`task-detail-dashboard ${aligned ? "initially-aligned" : ""}`}
      >
        <div className="task-detail-column task-detail-left">
          <DetailCard
            className="task-config-card"
            title={labels.config}
            summary={t("taskDetail.configSummary", {
              count: configEntries.length,
            })}
            icon={<Settings2 />}
            open={panels.config}
            onToggle={() => togglePanel("config")}
            actions={
              <button
                onClick={() => void copyConfig()}
                title={configCopied ? labels.copied : labels.copyConfig}
                aria-label={configCopied ? labels.copied : labels.copyConfig}
              >
                {configCopied ? <Check /> : <Copy />}
              </button>
            }
          >
            <div className="config-source">
              <span>{labels.task}</span>
              <code>{task.task_name}</code>
              <i>{labels.snapshot}</i>
            </div>
            {configEntries.length ? (
              <dl className="task-config-list">
                {configEntries.map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd title={formatConfigValue(value)}>
                      {formatConfigValue(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <div className="task-config-empty">
                <FileJson />
                {labels.noConfig}
              </div>
            )}
          </DetailCard>

          <DetailCard
            className="task-run-card"
            title={labels.runDetails}
            summary={`${completedSteps} ${labels.completedSteps}`}
            icon={
              <span className={`task-orb ${task.state}`}>
                {task.task_type.slice(0, 1).toUpperCase()}
              </span>
            }
            open={panels.details}
            onToggle={() => togglePanel("details")}
          >
            <div className="task-run-meta">
              <div>
                <small>{t("started")}</small>
                <strong>{formatDate(task.started_at)}</strong>
              </div>
              <div>
                <small>{t("duration")}</small>
                <strong>{formatDuration(task, t)}</strong>
              </div>
              <div>
                <small>EXIT CODE</small>
                <strong>{task.exit_code}</strong>
              </div>
            </div>
            {progress && (
              <div className="task-current-step">
                <span>{t("progress")}</span>
                <code title={progress.name}>{progress.name}</code>
                <strong>{progress.percentage}%</strong>
              </div>
            )}
            <DetailSection title={t("steps")}>
              <div className="step-list">
                {task.steps.length ? (
                  task.steps.map((step, index) => {
                    const percentage = Math.max(
                      0,
                      Math.min(100, step.percentage ?? 0),
                    );
                    const failed =
                      task.state === "failed" &&
                      index === task.steps.length - 1;
                    const done = !failed && step.percentage === 100;
                    return (
                      <div
                        className={`step-item ${failed ? "failed" : ""}`}
                        key={`${step.name}-${index}`}
                      >
                        <span
                          className={
                            failed ? "failed" : done ? "done" : "active"
                          }
                          style={
                            !failed && !done
                              ? ({
                                  "--step-progress": `${percentage}%`,
                                } as React.CSSProperties)
                              : undefined
                          }
                        >
                          {failed ? <X /> : done ? <Check /> : index + 1}
                        </span>
                        <div>
                          <strong>{step.name}</strong>
                          <small>
                            {failed
                              ? task.error || t("error")
                              : step.finished_at
                                ? formatDate(step.finished_at)
                                : step.started_at
                                  ? `${Math.round(percentage)}%`
                                  : t("notStarted")}
                          </small>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <p className="muted">{t("notStarted")}</p>
                )}
              </div>
            </DetailSection>
            {Object.keys(task.result).length > 0 && (
              <DetailSection title={t("result")}>
                <pre>{JSON.stringify(task.result, null, 2)}</pre>
              </DetailSection>
            )}
          </DetailCard>
        </div>

        <div className="task-detail-column task-detail-right">
          <DetailCard
            className="task-relations-card"
            title={labels.relations}
            summary={labels.relationsSummary}
            icon={<GitBranch />}
            open={panels.relations}
            onToggle={() => togglePanel("relations")}
            actions={
              <button
                onClick={locateCurrentTask}
                title={t("taskGraph.locate_current_task")}
                aria-label={t("taskGraph.locate_current_task")}
              >
                <LocateFixed />
              </button>
            }
          >
            <TaskGraphPanel
              taskId={taskId}
              remoteIp={remoteIp}
              locateRequest={locateRequest}
              onOpenTask={onOpenTask}
              onConnection={onConnection}
            />
          </DetailCard>

          <DetailCard
            className="task-log-card"
            title={labels.logs}
            summary={task.log_path || labels.logUnavailable}
            icon={<FileText />}
            open={panels.logs}
            onToggle={() => togglePanel("logs")}
            actions={
              <>
                <label className="log-follow">
                  <input
                    type="checkbox"
                    checked={followTail}
                    onChange={(event) => setFollowTail(event.target.checked)}
                  />
                  {labels.follow}
                </label>
                <button
                  onClick={() => void copyLog()}
                  disabled={!logText}
                  title={copied ? labels.copied : labels.copy}
                  aria-label={copied ? labels.copied : labels.copy}
                >
                  {copied ? <Check /> : <Copy />}
                </button>
              </>
            }
          >
            <div className="log-panel">
              <div className="log-meta">
                <span>
                  {labels.loaded}{" "}
                  {formatBytes(
                    Math.min(fileSize, Math.max(0, nextOffset - startOffset)),
                  )}{" "}
                  {labels.of} {formatBytes(fileSize)}
                </span>
                <span>{labels.bounded}</span>
              </div>
              {hasEarlier && !trimmed && (
                <button
                  className="load-earlier"
                  onClick={() =>
                    void loadLog(
                      Math.max(0, startOffset - LOG_CHUNK_BYTES),
                      "prepend",
                    )
                  }
                  disabled={
                    logLoading || logText.length > MAX_LOG_CHARACTERS - 1024
                  }
                >
                  <ChevronUp />
                  {labels.loadEarlier}
                </button>
              )}
              {logError ? (
                <div className="log-placeholder error">
                  <strong>{labels.logError}</strong>
                  <span>{logError}</span>
                </div>
              ) : !task.log_path ? (
                <div className="log-placeholder">{labels.logUnavailable}</div>
              ) : !logText && !logLoading ? (
                <div className="log-placeholder">{labels.logEmpty}</div>
              ) : (
                <pre className="log-content" ref={logViewport}>
                  {logText}
                  {logLoading && <span className="log-cursor" />}
                </pre>
              )}
            </div>
          </DetailCard>
        </div>
      </div>
    </section>
  );
}

function DetailCard({
  className,
  title,
  summary,
  icon,
  open,
  onToggle,
  actions,
  children,
}: {
  className: string;
  title: string;
  summary: React.ReactNode;
  icon: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const contentId = `${className}-content`;
  return (
    <section
      className={`task-detail-card ${className} ${open ? "open" : "collapsed"}`}
    >
      <header>
        <button
          className="task-detail-card-toggle"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={contentId}
        >
          <span className="task-detail-card-icon">{icon}</span>
          <span>
            <strong>{title}</strong>
            <small>{summary}</small>
          </span>
        </button>
        {actions && <div className="task-detail-card-actions">{actions}</div>}
        <button
          className="task-detail-card-chevron"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={contentId}
          aria-label={title}
        >
          <ChevronDown />
        </button>
      </header>
      {open && (
        <div className="task-detail-card-body" id={contentId}>
          {children}
        </div>
      )}
    </section>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}
function formatConfigValue(value: unknown) {
  if (typeof value === "string") return value || '""';
  return JSON.stringify(value);
}
