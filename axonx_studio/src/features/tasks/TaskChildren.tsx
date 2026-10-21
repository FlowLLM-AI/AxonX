import { useTranslation } from "react-i18next";
import { Status } from "./TaskRow";
import type { ChildTaskRecord } from "./types";

/** Show the latest invocation of each direct child; details belong to its own page. */
export function TaskChildren({
  records,
  onOpenTask,
}: {
  records: ChildTaskRecord[];
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const latest = [
    ...new Map(records.map((record) => [record.node_name, record])).values(),
  ];
  return (
    <div className="step-list">
      {latest.length ? (
        latest.map((record, index) => (
          <div className="step-item" key={record.node_name}>
            <span>{index + 1}</span>
            <div>
              <strong>{record.node_name}</strong>
              {record.task_id ? (
                <button
                  className="child-task-link"
                  onClick={() => onOpenTask(record.task_id!)}
                >
                  {record.task_id}
                </button>
              ) : (
                <code>{record.task}</code>
              )}
              {record.error && (
                <small className="error-state">{record.error}</small>
              )}
            </div>
            <Status state={record.state} />
          </div>
        ))
      ) : (
        <p className="muted">{t("taskDetail.noChildren")}</p>
      )}
    </div>
  );
}
