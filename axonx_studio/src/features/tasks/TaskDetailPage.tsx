import { TaskLogPanel } from "./TaskLogPanel";
import { TaskSteps } from "./TaskSteps";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { TaskQuality } from "../online/QualityReport";
import { isOnlineTask } from "../online/types";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  Ban,
  Check,
  ChevronDown,
  Copy,
  FileJson,
  FileText,
  GitBranch,
  Bot,
  LoaderCircle,
  LocateFixed,
  ArrowUpRight,
  Settings2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import type { TaskMetadata } from "./types";
import { usePolling } from "../../shared/hooks/usePolling";
import { cancelTask, getTaskStatus } from "./api";
import { formatDate, formatDuration, taskStepProgress } from "./format";
import { Status } from "./TaskRow";
import { TaskGraphPanel } from "../task-graph/TaskGraphPage";

const ACTIVE = new Set(["queued", "running"]);

export function TaskDetailPage({
  taskId,
  target,
  onBack,
  onOpenTask,
  onInterpretTask,
  onOpenResearch,
  onConnection,
}: {
  taskId: string;
  target?: string;
  onBack: () => void;
  onOpenTask: (taskId: string) => void;
  onInterpretTask: (taskId: string) => void;
  onOpenResearch: (taskType: string, taskId: string) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const labels = t("taskDetail", { returnObjects: true }) as Record<
    string,
    string
  >;
  const [task, setTask] = useState<TaskMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const configClipboard = useCopyFeedback();
  const configCopied = configClipboard.copied === "config";
  const [locateRequest, setLocateRequest] = useState(0);
  const [panels, setPanels] = useState({
    config: false,
    relations: false,
    details: true,
    logs: true,
  });

  const hasResearch =
    task?.state === "succeeded" &&
    ["etl", "analysis", "train", "predict", "backtest"].includes(
      task.task_type,
    ) &&
    Object.keys(task.output_params).length > 0;

  const loadStatus = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      try {
        const result = await getTaskStatus(taskId, target, signal);
        signal?.throwIfAborted();
        setTask(result);
        setError("");
        onConnection(true);
        return result;
      } catch (reason) {
        if (signal?.aborted) return null;
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [onConnection, target, taskId],
  );

  const refreshStatus = useCallback(
    async (signal: AbortSignal) => {
      await loadStatus(signal);
    },
    [loadStatus],
  );
  usePolling(refreshStatus, true);
  useEffect(() => {
    const controller = new AbortController();
    void loadStatus(controller.signal);
    return () => controller.abort();
  }, [loadStatus]);
  const copyConfig = async () => {
    if (!task) return;
    await configClipboard.copy(
      JSON.stringify(task.input_params || {}, null, 2),
      "config",
    );
  };
  const cancel = async () => {
    if (!task || !window.confirm(t("cancelConfirm"))) return;
    setCancelling(true);
    try {
      const cancelled = await cancelTask(task.run_id, target);
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
  const configEntries = Object.entries(task.input_params || {});
  const executionSteps = task.steps.filter((step) => !step.parent);
  const completedSteps = executionSteps.filter(
    (step) => step.percentage === 100,
  ).length;
  const togglePanel = (panel: keyof typeof panels) => {
    setPanels((current) => ({ ...current, [panel]: !current[panel] }));
  };
  const locateCurrentTask = () => {
    setPanels((current) => ({ ...current, relations: true }));
    setLocateRequest((current) => current + 1);
  };

  return (
    <section className="workspace-page task-detail-page">
      <ReplicaNotice replica={task.replica} state={task.state} />
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
            {task.pid || "—"} ·{" "}
            {task.source.schedule
              ? t("schedules.scheduledSource", {
                  name: task.source.schedule.name,
                })
              : t(`schedules.sources.${task.source.kind}`)}
          </span>
        </div>
        <div className="task-detail-heading-actions">
          {(hasResearch || isOnlineTask(task)) && (
            <button
              className="secondary-button"
              onClick={() =>
                onOpenResearch(
                  isOnlineTask(task) ? "online" : task.task_type,
                  task.task_id,
                )
              }
            >
              <ArrowUpRight />
              {labels.openResearch}
            </button>
          )}
          <button
            className="secondary-button"
            onClick={() => onInterpretTask(task.task_id)}
          >
            <Bot />
            {t("agent.interpretTask")}
          </button>
          {ACTIVE.has(task.state) && !task.replica && (
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
      <div className="task-detail-dashboard">
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
            <code>{task.reg_name}</code>
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
            target={target}
            locateRequest={locateRequest}
            onOpenTask={onOpenTask}
            onInterpretTask={onInterpretTask}
            onConnection={onConnection}
          />
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
              {executionSteps.length ? (
                executionSteps.map((step, index) => {
                  const percentage = Math.max(
                    0,
                    Math.min(100, step.percentage ?? 0),
                  );
                  const failed =
                    task.state === "failed" &&
                    index === executionSteps.length - 1;
                  const done = !failed && step.percentage === 100;
                  return (
                    <div
                      className={`step-item ${failed ? "failed" : ""}`}
                      key={`${step.name}-${index}`}
                    >
                      <span
                        className={failed ? "failed" : done ? "done" : "active"}
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
          {task.children.length > 0 && (
            <DetailSection title={t("taskDetail.children")}>
              <div className="step-list">
                {task.children.map((child, index) => (
                  <div className="step-item" key={child.run_id}>
                    <span>{index + 1}</span>
                    <div>
                      <strong>
                        {child.node_name} · {child.attempt}
                      </strong>
                      {child.task_id ? (
                        <button
                          className="child-task-link"
                          onClick={() => onOpenTask(child.task_id!)}
                        >
                          {child.task_id}
                        </button>
                      ) : (
                        <code>{child.task}</code>
                      )}
                      <small>{child.run_id}</small>
                      {child.error && <small>{child.error}</small>}
                    </div>
                    <Status state={child.state} />
                  </div>
                ))}
              </div>
            </DetailSection>
          )}
          <TaskSteps steps={task.steps.filter((step) => step.parent)} />
          <TaskQuality
            windows={task.output_params.windows}
            taskId={task.task_id}
            target={target}
          />
          {Object.keys(task.output_params).length > 0 && (
            <DetailSection title={t("result")}>
              <pre>{JSON.stringify(task.output_params, null, 2)}</pre>
            </DetailSection>
          )}
        </DetailCard>

        <DetailCard
          className="task-log-card"
          title={labels.logs}
          summary={
            task.replica
              ? t("replica.logUnavailable")
              : task.log_path || labels.logUnavailable
          }
          icon={<FileText />}
          open={panels.logs}
          onToggle={() => togglePanel("logs")}
        >
          <TaskLogPanel
            key={`${target}:${task.task_id}:${task.run_id}`}
            task={task}
            target={target}
          />
        </DetailCard>
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
