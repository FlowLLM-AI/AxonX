import { ArrowRight, Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TaskSummary } from "../../shared/api/contracts";
import { formatDateTime as formatDate } from "../../shared/lib/format";
import { Status } from "../tasks/TaskRow";

export function OperationIndex({
  tasks,
  selected,
  onSelected,
}: {
  tasks: TaskSummary[];
  selected?: string;
  onSelected: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="operation-index-list">
      {tasks.map((task) => (
        <article
          key={task.task_id}
          className={selected === task.task_id ? "active" : ""}
        >
          <button
            className="task-main rail-list-item"
            aria-pressed={selected === task.task_id}
            onClick={() => onSelected(task.task_id)}
          >
            <span className="task-item-avatar rail-avatar">
              <Play />
            </span>
            <span className="rail-item-copy">
              <strong>{task.display_name || task.reg_name}</strong>
              <small>{formatDate(task.started_at || task.created_at)}</small>
              <span className="operation-task-footer">
                <span>{t("operations.taskRecord")}</span>
                <Status state={task.state} />
              </span>
            </span>
            <ArrowRight />
          </button>
        </article>
      ))}
    </div>
  );
}
