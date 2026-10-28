import {
  ArrowLeft,
  ArrowUpRight,
  Bot,
  Check,
  Copy,
  FileJson,
  FileText,
  GitBranch,
  LoaderCircle,
  LocateFixed,
  RefreshCw,
  Settings2,
} from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { ReportTabs } from "../../shared/ui/ReportTabs";
import { getTaskStatus } from "./api";
import { ExecutionSteps } from "./ExecutionSteps";
import { hasTaskReport } from "./model";
import { TaskChildren } from "./TaskChildren";
import { TaskGraphPanel } from "./TaskGraph";
import { TaskLogPanel } from "./TaskLogPanel";
import { Status } from "./TaskRow";

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
  const configClipboard = useCopyFeedback();
  const configCopied = configClipboard.copied === "config";
  const [locateRequest, setLocateRequest] = useState(0);

  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const result = await getTaskStatus(taskId, { target, signal });
        signal.throwIfAborted();
        onConnection(true);
        return result;
      } catch (reason) {
        if (!signal.aborted) onConnection(false);
        throw reason;
      }
    },
    [onConnection, target, taskId],
  );

  const {
    data: task,
    loading,
    error: requestError,
    reload: loadStatus,
  } = useAsyncResource(load);
  const refreshAll = useRefresh(loadStatus);
  const error = requestError;
  const hasResearch =
    task?.state === "succeeded" &&
    ["etl", "analysis", "train", "predict", "backtest"].includes(
      task.task_type,
    ) &&
    Object.keys(task.output_params).length > 0;
  const copyConfig = async () => {
    if (!task) return;
    await configClipboard.copy(
      JSON.stringify(task.input_params || {}, null, 2),
      "config",
    );
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
          <button onClick={() => void loadStatus()}>{t("retry")}</button>
        </div>
      </section>
    );
  const configEntries = Object.entries(task.input_params || {});
  const locateCurrentTask = () => {
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
            {task.pid || "—"}
          </span>
        </div>
      </div>
      {error && (
        <div className="error-banner">
          <strong>{t("requestFailed")}</strong>
          <span>{error}</span>
          <button onClick={() => void loadStatus()}>{t("retry")}</button>
        </div>
      )}
      <div className="task-detail-tabs">
        <ReportTabs
          key={`${target}:${taskId}`}
          defaultTab="details"
          ariaLabel={t("taskTitle")}
          actions={
            <div className="task-detail-heading-actions">
              <button
                className="secondary-button"
                onClick={() => void refreshAll()}
                disabled={loading}
              >
                <RefreshCw className={loading ? "spin" : ""} />
                {t("refresh")}
              </button>
              {(hasResearch || hasTaskReport(task)) && (
                <button
                  className="secondary-button"
                  onClick={() =>
                    onOpenResearch(
                      hasTaskReport(task) ? "report" : task.task_type,
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
            </div>
          }
          tabs={[
            {
              id: "config",
              label: (
                <>
                  <Settings2 />
                  {labels.config}
                </>
              ),
              content: (
                <section className="task-detail-card open task-config-card">
                  <header className="task-detail-tab-summary">
                    <span>
                      {t("taskDetail.configSummary", {
                        count: configEntries.length,
                      })}
                    </span>
                    <div className="task-detail-card-actions">
                      <button
                        onClick={() => void copyConfig()}
                        title={configCopied ? labels.copied : labels.copyConfig}
                        aria-label={
                          configCopied ? labels.copied : labels.copyConfig
                        }
                      >
                        {configCopied ? <Check /> : <Copy />}
                      </button>
                    </div>
                  </header>
                  <div className="task-detail-card-body">
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
                  </div>
                </section>
              ),
            },
            {
              id: "relations",
              label: (
                <>
                  <GitBranch />
                  {labels.relations}
                </>
              ),
              content: (
                <section className="task-detail-card open task-relations-card">
                  <header className="task-detail-tab-summary">
                    <span>{labels.relationsSummary}</span>
                    <div className="task-detail-card-actions">
                      <button
                        onClick={locateCurrentTask}
                        title={t("taskGraph.locate_current_task")}
                        aria-label={t("taskGraph.locate_current_task")}
                      >
                        <LocateFixed />
                      </button>
                    </div>
                  </header>
                  <div className="task-detail-card-body">
                    <TaskGraphPanel
                      taskId={taskId}
                      target={target}
                      locateRequest={locateRequest}
                      onOpenTask={onOpenTask}
                      onInterpretTask={onInterpretTask}
                      onConnection={onConnection}
                    />
                  </div>
                </section>
              ),
              lazy: true,
            },
            {
              id: "details",
              label: (
                <>
                  <span className={`task-orb ${task.state}`}>
                    {task.task_type.slice(0, 1).toUpperCase()}
                  </span>
                  {labels.taskDetails}
                </>
              ),
              content: (
                <section className="task-detail-card open task-execution-card">
                  <div className="task-detail-card-body">
                    {task.error && (
                      <p className="error-state" role="alert">
                        {task.error}
                      </p>
                    )}
                    <h3>{t("steps")}</h3>
                    <ExecutionSteps
                      key={`${target}:${task.started_at}`}
                      task={task}
                    />
                    {task.children.length > 0 && (
                      <>
                        <h3>{labels.children}</h3>
                        <TaskChildren
                          records={task.children}
                          onOpenTask={onOpenTask}
                        />
                      </>
                    )}
                  </div>
                </section>
              ),
            },
            {
              id: "logs",
              label: (
                <>
                  <FileText />
                  {labels.logs}
                </>
              ),
              content: (
                <section className="task-detail-card open task-log-card">
                  <div className="task-detail-card-body">
                    <TaskLogPanel
                      key={`${target}:${task.task_id}:${task.started_at}`}
                      task={task}
                      target={target}
                      toolbar={
                        <span className="task-log-path" title={task.log_path}>
                          {task.replica
                            ? t("replica.logUnavailable")
                            : task.log_path || labels.logUnavailable}
                        </span>
                      }
                    />
                  </div>
                </section>
              ),
            },
          ]}
        />
      </div>
    </section>
  );
}

function formatConfigValue(value: unknown) {
  if (typeof value === "string") return value || '""';
  return JSON.stringify(value);
}
