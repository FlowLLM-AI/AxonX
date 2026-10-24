import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import { formatDate, formatDuration, taskStepProgress } from "./format";
import type { TaskState, TaskSummary } from "./types";

export function TaskRow({
  task,
  onOpen,
}: {
  task: TaskSummary;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const progress = taskStepProgress(task);
  const clipboard = useCopyFeedback();
  const copied = clipboard.copied === task.task_id;
  return (
    <tr onClick={onOpen}>
      <td className="task-id-column">
        <div className="task-identity">
          <span className={`task-orb ${task.state}`}>
            {task.task_type.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <span className="task-id-line">
              <strong title={task.task_id}>
                {task.task_id.split("#")[2] || task.task_id}
              </strong>
              {task.is_replica && (
                <small className="replica-label">{t("replica.label")}</small>
              )}
              <button
                type="button"
                className={copied ? "copied" : ""}
                aria-label={copied ? t("copied") : t("copyTaskId")}
                title={copied ? t("copied") : t("copyTaskId")}
                onClick={(event) => {
                  event.stopPropagation();
                  void clipboard.copy(task.task_id);
                }}
              >
                {copied ? (
                  <>
                    <Check />
                    <span aria-live="polite">{t("copied")}</span>
                  </>
                ) : (
                  <Copy />
                )}
              </button>
            </span>
            <small>
              PID {task.pid || "—"} · {t(`taskSources.${task.source.kind}`)}
            </small>
          </div>
        </div>
      </td>
      <td className="state-column">
        <Status state={task.state} />
      </td>
      <td className="progress-column">
        {progress ? (
          <div className="progress-cell">
            <span className="progress-step">
              <small>{t("step")}</small>
              <strong>{progress.current}</strong>
            </span>
            <span
              className="progress-ring"
              style={
                {
                  "--step-progress": `${progress.percentage}%`,
                } as React.CSSProperties
              }
            >
              <strong>{progress.percentage}</strong>
              <small>%</small>
            </span>
          </div>
        ) : (
          <span className="muted">{t("notStarted")}</span>
        )}
      </td>
      <td className="started-column">
        {formatDate(task.started_at || task.created_at)}
      </td>
      <td className="duration-column">{formatDuration(task, t)}</td>
    </tr>
  );
}

export function Status({ state }: { state: TaskState }) {
  const { t } = useTranslation();
  return (
    <span className={`status-badge ${state}`}>
      <i />
      {t(`states.${state}`)}
    </span>
  );
}
