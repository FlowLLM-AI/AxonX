import { AlertTriangle, LoaderCircle, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TaskSummary } from "../../../shared/api/contracts";
export function ComparisonPicker({
  tasks,
  idA,
  idB,
  loading: listLoading,
  error: listError,
  onSelect: toggleTask,
  onRefresh: reloadList,
}: {
  tasks: TaskSummary[];
  idA: string;
  idB: string;
  loading: boolean;
  error: string;
  onSelect: (id: string) => void;
  onRefresh: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage === "zh" ? "zh-CN" : "en-US";
  const [query, setQuery] = useState("");
  const availableTasks = tasks.filter((task) =>
    `${task.task_id} ${task.display_name}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <aside className="compare-picker rail-panel task-index">
      <header className="task-index-header rail-header">
        <div className="task-index-heading rail-heading">
          <small>TASKS</small>
          <strong>{t("compare.task_list")}</strong>
        </div>
        <div className="task-index-tools">
          <em>{tasks.length}</em>
          <button
            type="button"
            className="task-index-refresh rail-refresh"
            onClick={() => void reloadList()}
            aria-label={t("compare.refresh_tasks")}
          >
            <RefreshCw className={listLoading ? "spin" : ""} />
          </button>
        </div>
      </header>
      <label className="task-index-search rail-search">
        <Search />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("compare.search_task_id")}
        />
      </label>
      <div className="compare-picker-list rail-scroll">
        <p className="compare-picker-hint">
          {t("compare.click_two_tasks_to_compare")}
        </p>
        {listLoading && (
          <p className="compare-state">
            <LoaderCircle className="spin" />
            {t("compare.loading_tasks")}
          </p>
        )}
        {listError && (
          <p className="compare-state error">
            <AlertTriangle />
            {listError}
          </p>
        )}
        {!listLoading && !listError && !tasks.length && (
          <p className="compare-state">{t("compare.no_backtests_available")}</p>
        )}
        {availableTasks.map((task) => (
          <article
            className={
              idA === task.task_id || idB === task.task_id ? "active" : ""
            }
            key={task.task_id}
          >
            <button
              className="task-main rail-list-item compare-task-item"
              type="button"
              aria-pressed={idA === task.task_id || idB === task.task_id}
              onClick={() => toggleTask(task.task_id)}
            >
              <span className="task-item-avatar rail-avatar task-kind-backtest">
                {task.reg_name.slice(0, 1).toUpperCase()}
              </span>
              <span className="rail-item-copy">
                <strong>{task.reg_name}</strong>
                <code title={task.task_id}>{task.task_id}</code>
                <small>
                  {task.created_at
                    ? new Date(task.created_at).toLocaleString(locale)
                    : t("compare.metadata_unavailable")}
                </small>
              </span>
              <span
                className={`compare-slot-badge${idA === task.task_id ? " slot-a" : idB === task.task_id ? " slot-b" : ""}`}
              >
                {idA === task.task_id ? "A" : idB === task.task_id ? "B" : "+"}
              </span>
            </button>
          </article>
        ))}
      </div>
    </aside>
  );
}
