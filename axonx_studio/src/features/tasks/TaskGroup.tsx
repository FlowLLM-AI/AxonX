import { useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Layers } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ACTIVE, STATES, type TaskGroupData } from "./groups";
import { formatDate } from "./format";
import { TaskRow } from "./TaskRow";
import type { TaskSummary } from "./types";

interface GroupProps {
  group: TaskGroupData;
  filterKey: string;
  selectionMode: boolean;
  selected: Set<string>;
  onToggle: (ids: string[]) => void;
  onOpenTask: (taskId: string) => void;
  onGroupContextMenu: (event: React.MouseEvent<HTMLElement>) => void;
  onContextMenu: (
    task: TaskSummary,
    event: React.MouseEvent<HTMLTableRowElement>,
  ) => void;
}

export function GroupSelection({
  ids,
  selected,
  onToggle,
  label,
}: {
  ids: string[];
  selected: Set<string>;
  onToggle: (ids: string[]) => void;
  label: string;
}) {
  const count = ids.filter((id) => selected.has(id)).length;
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={ids.length > 0 && count === ids.length}
      disabled={!ids.length}
      ref={(input) => {
        if (input) input.indeterminate = count > 0 && count < ids.length;
      }}
      onChange={() => onToggle(ids)}
    />
  );
}

export function TaskGroup(props: GroupProps) {
  const { group, filterKey, selectionMode, selected, onToggle } = props;
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(group.active > 0);
  const latest = group.tasks[0];
  const ids = group.tasks
    .filter((task) => !ACTIVE.has(task.state))
    .map((task) => task.task_id);
  return (
    <section className={`task-group ${expanded ? "expanded" : ""}`}>
      <header
        className="task-group-header"
        onContextMenu={props.onGroupContextMenu}
      >
        {selectionMode && (
          <GroupSelection
            ids={ids}
            selected={selected}
            onToggle={onToggle}
            label={t("taskGroups.selectGroup", { group: group.key })}
          />
        )}
        <button
          className="task-group-toggle"
          aria-expanded={expanded}
          aria-label={group.key}
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronDown className="task-group-chevron" size={16} />
          <span className="task-group-icon">
            <Layers size={19} />
          </span>
          <span className="task-group-title">
            <strong title={group.key}>{group.key}</strong>
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
          <span className="task-group-latest">
            <small>{t("taskGroups.latest")}</small>
            <span>
              {formatDate(
                latest.started_at || latest.created_at || latest.finished_at,
              )}
            </span>
          </span>
        </button>
      </header>
      <GroupMembers key={filterKey} {...props} expanded={expanded} />
    </section>
  );
}

const PAGE_SIZE = 50;
function GroupMembers({
  group,
  selectionMode,
  selected,
  onToggle,
  onOpenTask,
  onContextMenu,
  expanded,
}: GroupProps & { expanded: boolean }) {
  const { t } = useTranslation();
  const [position, setPosition] = useState(0);
  if (!expanded) return null;
  const pages = Math.ceil(group.tasks.length / PAGE_SIZE);
  const page = Math.min(position, pages - 1);
  const tasks = group.tasks.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  return (
    <div className="task-group-members">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {selectionMode && <th className="select-column" />}
              <th className="task-id-column">{t("taskGroups.name")}</th>
              <th className="state-column">{t("state")}</th>
              <th className="progress-column">{t("progress")}</th>
              <th className="started-column">{t("started")}</th>
              <th className="duration-column">{t("duration")}</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <TaskRow
                key={task.task_id}
                task={task}
                selectionMode={selectionMode}
                selected={selected.has(task.task_id)}
                onSelect={() => onToggle([task.task_id])}
                onOpen={() => onOpenTask(task.task_id)}
                onContextMenu={(event) => onContextMenu(task, event)}
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
              end: Math.min((page + 1) * PAGE_SIZE, group.tasks.length),
              count: group.tasks.length,
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
