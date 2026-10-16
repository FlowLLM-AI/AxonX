import { useState, type ReactNode } from "react";
import {
  ArrowRight,
  ChevronRight,
  Clock,
  Hand,
  History,
  Play,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import { runDate, type OperationRun, type OperationGroup } from "./tree";

function Branch({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <details
      className={`operation-group ${className}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      {children}
    </details>
  );
}

function RunRow({
  run,
  selected,
  onSelected,
}: {
  run: OperationRun;
  selected?: string;
  onSelected: (id: string) => void;
}) {
  const { t } = useTranslation();
  const state = run.kind === "task" ? run.task.state : run.run.state;
  return (
    <article
      className={selected === run.id ? "active" : ""}
      data-kind={run.kind}
    >
      <button
        className="run-main rail-list-item"
        aria-pressed={selected === run.id}
        onClick={() => onSelected(run.id)}
      >
        <span className="run-item-avatar rail-avatar">
          <Play />
        </span>
        <span className="rail-item-copy">
          <strong>{formatDate(runDate(run))}</strong>
          <small>
            {run.kind === "task"
              ? run.task.display_name || run.task.reg_name
              : run.run.job}
          </small>
          <small>
            {t(
              run.kind === "task" ? "operations.taskRun" : "operations.jobRun",
            )}
          </small>
          <Status state={state} />
        </span>
        <ArrowRight />
      </button>
    </article>
  );
}

export function OperationTree({
  groups,
  manual,
  showManual,
  selected,
  onSelected,
}: {
  groups: OperationGroup[];
  manual: OperationRun[];
  showManual: boolean;
  selected?: string;
  onSelected: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      {groups.length > 0 && (
        <h3 className="operation-index-label">{t("operations.schedules")}</h3>
      )}
      {groups.map((group) => (
        <Branch key={group.id}>
          <summary>
            <ChevronRight className="operation-chevron" />
            <button
              className={`operation-schedule rail-list-item${selected === group.id ? " active" : ""}`}
              aria-pressed={selected === group.id}
              onClick={(event) => {
                event.preventDefault();
                onSelected(group.id);
              }}
            >
              {group.archived ? <History /> : <Clock />}
              <span className="rail-item-copy">
                <strong>{group.name}</strong>
                <small>
                  {group.archived
                    ? t("operations.archived")
                    : group.schedule?.cron || t("schedules.removed")}
                </small>
              </span>
              <em>{group.runs.length}</em>
            </button>
          </summary>
          <div className="operation-runs">
            {group.runs.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                selected={selected}
                onSelected={onSelected}
              />
            ))}
            {!group.runs.length && (
              <p className="operation-index-empty">{t("operations.noRuns")}</p>
            )}
          </div>
        </Branch>
      ))}
      {showManual && (
        <Branch className="operation-manual">
          <summary>
            <ChevronRight className="operation-chevron" />
            <Hand />
            <strong>{t("operations.manual")}</strong>
            <em>{manual.length}</em>
          </summary>
          <div className="operation-runs">
            {manual.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                selected={selected}
                onSelected={onSelected}
              />
            ))}
            {!manual.length && (
              <p className="operation-index-empty">{t("operations.noRuns")}</p>
            )}
          </div>
        </Branch>
      )}
    </>
  );
}
