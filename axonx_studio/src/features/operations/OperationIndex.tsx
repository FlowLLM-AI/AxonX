import { ArrowRight, Clock, Play, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import { entryDate, entryLabel, type OperationEntry } from "./model";

export function OperationIndex({
  entries,
  selected,
  onSelected,
}: {
  entries: OperationEntry[];
  selected?: string;
  onSelected: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="operation-index-list">
      {entries.map((entry) => (
        <article
          key={entry.id}
          className={selected === entry.id ? "active" : ""}
          data-kind={entry.kind}
        >
          <button
            className="run-main rail-list-item"
            aria-pressed={selected === entry.id}
            onClick={() => onSelected(entry.id)}
          >
            <span className="run-item-avatar rail-avatar">
              {entry.kind === "task" ? (
                <Play />
              ) : entry.kind === "job" ? (
                <RefreshCw />
              ) : (
                <Clock />
              )}
            </span>
            <span className="rail-item-copy">
              <strong>{entryLabel(entry)}</strong>
              <small>
                {entry.kind === "schedule"
                  ? entry.schedules[0]
                    ? `${t("operations.configurationShort")} · ${entry.schedules[0].cron}`
                    : t("schedules.removed")
                  : formatDate(entryDate(entry))}
              </small>
              {entry.kind !== "schedule" && (
                <span className="operation-run-footer">
                  <span>
                    {t(
                      entry.kind === "task"
                        ? "operations.taskRun"
                        : "operations.jobRun",
                    )}
                  </span>
                  <Status
                    state={
                      entry.kind === "task" ? entry.task.state : entry.run.state
                    }
                  />
                </span>
              )}
            </span>
            <ArrowRight />
          </button>
        </article>
      ))}
    </div>
  );
}
