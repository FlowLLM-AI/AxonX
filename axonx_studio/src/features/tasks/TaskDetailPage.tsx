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
  LoaderCircle,
  Play,
  RefreshCw,
  RotateCw,
  Settings2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatBytes } from "../../shared/lib/format";
import { isAbortError } from "../../shared/lib/errors";
import type { JobEvent } from "../../shared/api/event";
import type { TaskStatus } from "./types";
import {
  cancelTask,
  getTaskStatus,
  readTaskLog,
  streamTask,
  submitTask,
} from "./api";
import { formatDate, formatDuration, taskStepProgress } from "./format";
import { Status } from "./TasksPage";
import { TaskGraphPanel } from "../task-graph/TaskGraphPage";

const ACTIVE = new Set(["queued", "running"]);
const LOG_CHUNK_BYTES = 65_536;
const MAX_LOG_CHARACTERS = 524_288;

export function TaskDetailPage({
  taskId,
  tab,
  remoteIp,
  onBack,
  onTabChange,
  onOpenTask,
  onConnection,
}: {
  taskId: string;
  tab: "overview" | "logs" | "relations";
  remoteIp?: string;
  onBack: () => void;
  onTabChange: (tab: "overview" | "logs" | "relations") => void;
  onOpenTask: (taskId: string) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const labels = t("taskDetail", { returnObjects: true }) as Record<
    string,
    string
  >;
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
  const [configOpen, setConfigOpen] = useState(false);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [rerunMessage, setRerunMessage] = useState("");
  const logViewport = useRef<HTMLPreElement>(null);
  const logRequest = useRef(false);
  const logLength = useRef(0);
  const taskState = task?.state;

  const loadStatus = useCallback(
    async (quiet = false) => {
      if (quiet) setRefreshing(true);
      else setLoading(true);
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
        setRefreshing(false);
      }
    },
    [onConnection, remoteIp, taskId],
  );

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
    setConfigOpen(false);
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
        void loadStatus(true);
      });
    return () => controller.abort();
  }, [loadStatus, onConnection, remoteIp, taskId, taskState]);
  useEffect(() => {
    if (followTail && logViewport.current)
      logViewport.current.scrollTop = logViewport.current.scrollHeight;
  }, [followTail, logText]);

  const refresh = async () => {
    const result = await loadStatus(true);
    if (result?.log_path) await loadLog(-1, "replace");
  };
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
  const rerun = async () => {
    if (!task?.task_name) return;
    setRerunning(true);
    setRerunMessage("");
    try {
      const config = { ...task.config };
      delete config.task_name;
      await submitTask(task.task_name, config, remoteIp);
      setRerunOpen(false);
      setRerunMessage(labels.rerunSubmitted);
      onConnection(true);
    } catch (reason) {
      setRerunMessage(
        `${labels.rerunFailed}: ${reason instanceof Error ? reason.message : String(reason)}`,
      );
      onConnection(false);
    } finally {
      setRerunning(false);
    }
  };
  const cancel = async () => {
    if (!task || !window.confirm(t("cancelConfirm"))) return;
    setCancelling(true);
    try {
      const cancelled = await cancelTask(task.task_id, remoteIp);
      if (!cancelled) throw new Error(t("cancelFailed"));
      await refresh();
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
  const canRerun = Boolean(task.task_name);
  const completedSteps = task.steps.filter(
    (step) => step.percentage === 100,
  ).length;

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
          <span>
            {t(`types.${task.task_type}`, task.task_type)} · PID{" "}
            {task.pid || "—"}
          </span>
        </div>
        <div className="heading-actions">
          <button
            className="secondary-button task-detail-icon-button"
            onClick={() => void refresh()}
            disabled={refreshing}
            title={t("refreshNow")}
            aria-label={t("refreshNow")}
          >
            <RefreshCw className={refreshing ? "spin" : ""} />
          </button>
          {ACTIVE.has(task.state) ? (
            <button
              className="danger-outline task-detail-icon-button"
              onClick={() => void cancel()}
              disabled={cancelling}
              title={cancelling ? t("cancelling") : t("cancel")}
              aria-label={cancelling ? t("cancelling") : t("cancel")}
            >
              <Ban />
            </button>
          ) : (
            <button
              className="primary-button task-rerun-button"
              onClick={() => setRerunOpen(true)}
              disabled={!canRerun || rerunning}
              title={canRerun ? labels.rerun : labels.unavailableRerun}
            >
              <RotateCw />
              {labels.rerun}
            </button>
          )}
        </div>
      </div>
      {error && (
        <div className="error-banner">
          <strong>{t("requestFailed")}</strong>
          <span>{error}</span>
        </div>
      )}
      {rerunMessage && (
        <div
          className={`task-rerun-notice ${rerunMessage.startsWith(labels.rerunFailed) ? "error" : ""}`}
        >
          <Play />
          {rerunMessage}
        </div>
      )}
      <nav className="task-detail-tabs" aria-label={t("taskDetail.views")}>
        <button
          className={tab === "overview" ? "active" : ""}
          onClick={() => onTabChange("overview")}
        >
          <Settings2 />
          {labels.overview}
        </button>
        <button
          className={tab === "logs" ? "active" : ""}
          onClick={() => onTabChange("logs")}
        >
          <FileText />
          {labels.logs}
        </button>
        <button
          className={tab === "relations" ? "active" : ""}
          onClick={() => onTabChange("relations")}
        >
          <GitBranch />
          {labels.relations}
        </button>
      </nav>
      {tab === "relations" ? (
        <TaskGraphPanel
          taskId={taskId}
          remoteIp={remoteIp}
          onOpenTask={onOpenTask}
          onConnection={onConnection}
        />
      ) : (
        <div className={`task-detail-layout single-panel ${tab}`}>
          {tab === "overview" && (
            <div className="task-detail-summary">
              <section
                className={`task-config-section ${configOpen ? "open" : "collapsed"}`}
              >
                <header className="detail-section-heading">
                  <button
                    className="config-section-toggle"
                    type="button"
                    onClick={() => setConfigOpen((open) => !open)}
                    aria-expanded={configOpen}
                    aria-controls="task-config-content"
                    title={
                      configOpen ? labels.collapseConfig : labels.expandConfig
                    }
                  >
                    <span className="detail-section-icon">
                      <Settings2 />
                    </span>
                    <span>
                      <h2>{labels.config}</h2>
                      <p>{labels.effectiveConfig}</p>
                    </span>
                    <ChevronDown className="config-chevron" />
                  </button>
                  <button
                    className="config-copy-button"
                    onClick={() => void copyConfig()}
                  >
                    <Copy />
                    {configCopied ? labels.copied : labels.copyConfig}
                  </button>
                </header>
                {configOpen && (
                  <div id="task-config-content">
                    <div>
                      <div className="config-source">
                        <span>{t("taskDetail.task")}</span>
                        <code>{task.task_name}</code>
                        <i>{t("taskDetail.snapshot")}</i>
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
                    </div>
                  </div>
                )}
              </section>

              <section className="task-run-section">
                <header className="detail-section-heading run-heading">
                  <div>
                    <span className={`task-orb ${task.state}`}>
                      {task.task_type.slice(0, 1).toUpperCase()}
                    </span>
                    <div>
                      <h2>{labels.runDetails}</h2>
                      <p>
                        <Status state={task.state} /> · {completedSteps}{" "}
                        {labels.completedSteps}
                      </p>
                    </div>
                  </div>
                </header>
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
              </section>
            </div>
          )}
          {tab === "logs" && (
            <section className="log-panel">
              <header>
                <div>
                  <span className="log-title">
                    <FileText />
                    {labels.live}
                    {ACTIVE.has(task.state) && <i />}
                  </span>
                  <code title={task.log_path}>
                    {task.log_path || labels.logUnavailable}
                  </code>
                </div>
                <div>
                  <label className="log-follow">
                    <input
                      type="checkbox"
                      checked={followTail}
                      onChange={(event) => setFollowTail(event.target.checked)}
                    />
                    {labels.follow}
                  </label>
                  <button onClick={() => void copyLog()} disabled={!logText}>
                    <Copy />
                    {copied ? labels.copied : labels.copy}
                  </button>
                </div>
              </header>
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
            </section>
          )}
        </div>
      )}
      {rerunOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setRerunOpen(false);
          }}
        >
          <section
            className="confirm-modal rerun-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rerun-title"
          >
            <button
              className="close-button"
              onClick={() => setRerunOpen(false)}
              aria-label={t("close")}
            >
              <X />
            </button>
            <span className="rerun-icon">
              <RotateCw />
            </span>
            <h2 id="rerun-title">{labels.rerunConfirm}</h2>
            <p>{labels.rerunHint}</p>
            <div className="rerun-config-summary">
              <strong>{task.task_name}</strong>
              <span>
                {configEntries.length} {t("taskDetail.configurationValues")}
              </span>
            </div>
            <div>
              <button
                className="secondary-button"
                onClick={() => setRerunOpen(false)}
              >
                {t("close")}
              </button>
              <button
                className="primary-button"
                onClick={() => void rerun()}
                disabled={rerunning}
              >
                {rerunning ? <LoaderCircle className="spin" /> : <RotateCw />}
                {rerunning ? labels.rerunning : labels.confirmRerun}
              </button>
            </div>
          </section>
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
