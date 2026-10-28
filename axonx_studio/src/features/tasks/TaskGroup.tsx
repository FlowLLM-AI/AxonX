import { ChevronDown, ChevronLeft, ChevronRight, Layers } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TaskSummary } from "../../shared/api/contracts";
import { formatDateTime as formatDate } from "../../shared/lib/format";
import { STATES, type TaskGroupData } from "./model";
import { TaskRow } from "./TaskRow";

interface GroupProps {
  group: TaskGroupData;
  filterKey: string;
  onOpenTask: (taskId: string) => void;
}

export function TaskGroup(props: GroupProps) {
  const { group, filterKey } = props;
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(group.active > 0);
  const latest = group.tasks[0];
  const label = group.label || group.key;
  return (
    <section className={`task-group ${expanded ? "expanded" : ""}`}>
      <header className="task-group-header">
        <button
          className="task-group-toggle"
          aria-expanded={expanded}
          aria-label={label}
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronDown className="task-group-chevron" size={16} />
          <span className="task-group-icon">
            <Layers size={14} />
          </span>
          <span className="task-group-title">
            <strong title={label}>{label}</strong>
            <small>
              {t(`types.${group.type}`, group.type)} ·{" "}
              {t(
                group.tasks.length === group.total
                  ? "taskGroups.members"
                  : "taskGroups.matching",
                {
                  count: group.tasks.length,
                  total: group.total,
                },
              )}
            </small>
          </span>
          <span className="task-group-states">
            {STATES.filter((state) => group.counts[state]).map((state) => (
              <span key={state} className={`status-badge ${state}`}>
                <i />
                {t(`states.${state}`)} <b>{group.counts[state]}</b>
              </span>
            ))}
          </span>
          <span className="task-group-latest" title={t("taskGroups.latest")}>
            <span>
              {formatDate(
                latest.started_at || latest.created_at || latest.finished_at,
              )}
            </span>
          </span>
        </button>
      </header>
      <GroupTable
        key={filterKey}
        {...props}
        tasks={group.tasks}
        expanded={expanded}
      />
    </section>
  );
}

const PAGE_SIZE = 50;

export function TaskTableColumns() {
  return (
    <colgroup>
      <col className="task-id-column" />
      <col className="state-column" />
      <col className="progress-column" />
      <col className="started-column" />
      <col className="duration-column" />
    </colgroup>
  );
}

export function TaskTableHeading({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <thead className={className}>
      <tr>
        <th className="task-id-column" scope="col">
          {t("taskGroups.name")}
        </th>
        <th className="state-column" scope="col">
          {t("state")}
        </th>
        <th className="progress-column" scope="col">
          {t("progress")}
        </th>
        <th className="started-column" scope="col">
          {t("started")}
        </th>
        <th className="duration-column" scope="col">
          {t("duration")}
        </th>
      </tr>
    </thead>
  );
}

function GroupTable({
  group,
  tasks: members,
  onOpenTask,
  expanded,
}: GroupProps & { expanded: boolean; tasks: TaskSummary[] }) {
  const { t } = useTranslation();
  const [position, setPosition] = useState(0);
  if (!expanded) return null;
  const pages = Math.ceil(members.length / PAGE_SIZE);
  const page = Math.min(position, pages - 1);
  const tasks = members.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  return (
    <div className="task-group-members">
      <div className="table-wrap">
        <table aria-label={group.label || group.key}>
          <TaskTableColumns />
          <TaskTableHeading className="task-member-heading" />
          <tbody>
            {tasks.map((task) => (
              <TaskRow
                key={task.task_id}
                task={task}
                onOpen={() => onOpenTask(task.task_id)}
              />
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <footer className="task-group-pagination">
          <span>
            {t("taskGroups.range", {
              start: page * PAGE_SIZE + 1,
              end: Math.min((page + 1) * PAGE_SIZE, members.length),
              count: members.length,
            })}
          </span>
          <button
            className="secondary-button"
            aria-label={t("taskGroups.previous")}
            disabled={page === 0}
            onClick={() => setPosition(page - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          <span>
            {page + 1} / {pages}
          </span>
          <button
            className="secondary-button"
            aria-label={t("taskGroups.next")}
            disabled={page + 1 === pages}
            onClick={() => setPosition(page + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </footer>
      )}
    </div>
  );
}
