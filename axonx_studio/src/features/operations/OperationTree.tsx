import { useState, type ReactNode } from "react";
import { ArrowRight, ChevronRight, Clock, History, Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import { runDate, type OperationRun, type OperationGroup } from "./tree";

function Branch({
  children,
  flat = false,
}: {
  children: ReactNode;
  flat?: boolean;
}) {
  const [open, setOpen] = useState(true);
  if (flat)
    return (
      <div className="operation-group operation-group-flat">{children}</div>
    );
  return (
    <details
      className="operation-group"
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
        {run.kind === "job" ? (
          <>
            <time
              className="operation-job-time"
              dateTime={run.run.triggered_at}
            >
              {formatDate(runDate(run))}
            </time>
            <Status state={state} />
          </>
        ) : (
          <>
            <span className="run-item-avatar rail-avatar">
              <Play />
            </span>
            <span className="rail-item-copy">
              <strong>{run.task.display_name || run.task.reg_name}</strong>
              <small>{formatDate(runDate(run))}</small>
              <span className="operation-run-footer">
                <span>{t("operations.taskRun")}</span>
                <Status state={state} />
              </span>
            </span>
          </>
        )}
        <ArrowRight />
      </button>
    </article>
  );
}

export function OperationTree({
  groups,
  manual,
  selected,
  onSelected,
}: {
  groups: OperationGroup[];
  manual: OperationRun[];
  selected?: string;
  onSelected: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      {groups.map((group) => {
        const flat =
          group.runs.length > 0 &&
          group.runs.every((run) => run.kind === "job");
        const Heading = flat ? "div" : "summary";
        return (
          <Branch key={group.id} flat={flat}>
            <Heading className="operation-group-heading">
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
            </Heading>
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
                <p className="operation-index-empty">
                  {t("operations.noRuns")}
                </p>
              )}
            </div>
          </Branch>
        );
      })}
      {manual.length > 0 && (
        <div className="operation-runs operation-ungrouped">
          {manual.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              selected={selected}
              onSelected={onSelected}
            />
          ))}
        </div>
      )}
    </>
  );
}
