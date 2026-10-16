import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import { canDelete } from "./groups";
import { formatDate, formatDuration, taskStepProgress } from "./format";
import type { TaskState, TaskSummary } from "./types";

export function TaskRow({
  task,
  selectionMode,
  selected,
  onSelect,
  onOpen,
  onContextMenu,
}: {
  task: TaskSummary;
  selectionMode: boolean;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
  onContextMenu: (event: React.MouseEvent<HTMLTableRowElement>) => void;
}) {
  const { t } = useTranslation();
  const progress = taskStepProgress(task);
  const selectable = canDelete(task);
  const clipboard = useCopyFeedback();
  const copied = clipboard.copied === task.task_id;
  return (
    <tr
      className={selected ? "selected" : ""}
      onClick={selectionMode ? (selectable ? onSelect : undefined) : onOpen}
      onContextMenu={onContextMenu}
    >
      {selectionMode && (
        <td
          className="select-column"
          onClick={(event) => event.stopPropagation()}
        >
          <input
            type="checkbox"
            aria-label={t("selectTask", { taskId: task.task_id })}
            checked={selected}
            disabled={!selectable}
            onChange={onSelect}
          />
        </td>
      )}
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
              <small className="replica-label">
                {t(
                  task.managed_run_id
                    ? "taskOwnership.managed"
                    : "taskOwnership.workspace",
                )}
              </small>
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
              PID {task.pid || "—"} ·{" "}
              {task.source.schedule
                ? t("schedules.scheduledSource", {
                    name: task.source.schedule.name,
                  })
                : t(`schedules.sources.${task.source.kind}`)}
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
