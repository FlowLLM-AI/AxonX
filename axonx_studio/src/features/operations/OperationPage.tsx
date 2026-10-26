import { useCallback, useEffect, useState } from "react";
import { Activity, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OperationPageDefinition } from "./pages";
import type { TaskSummary } from "../tasks/types";
import { listTaskStatuses } from "../tasks/api";
import { formatDate } from "../tasks/format";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { RailResizer } from "../../shared/ui/RailResizer";
import { TaskIndexControls } from "../../shared/ui/TaskIndexControls";
import { PipelineReport } from "../online/PipelineReport";
import { TaskReport } from "./TaskReport";
import { OperationIndex } from "./OperationIndex";
import type { ContextOption } from "../../app/types";

const EMPTY_TASKS: TaskSummary[] = [];

export default function OperationPage({
  page,
  target,
  initialResource,
  onSelected,
  onOptionsChange,
  onConnection,
  onOpenTask,
}: {
  page: OperationPageDefinition;
  target?: string;
  initialResource?: string;
  onSelected: (id: string) => void;
  onOptionsChange: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const tasks = await listTaskStatuses(target, signal);
        signal.throwIfAborted();
        onConnection(true);
        return tasks
          .filter(
            (task) =>
              page.reportKinds.includes(task.report_kind || "") &&
              !task.parent_task_id &&
              (task.report_kind !== "online" || task.task_type === "inference"),
          )
          .sort((a, b) =>
            (b.created_at || "").localeCompare(a.created_at || ""),
          );
      } catch (reason) {
        if (!signal.aborted) onConnection(false);
        throw reason;
      }
    },
    [target, page, onConnection],
  );
  const { data, loading, error, reload } = useAsyncResource(load);
  const refreshAll = useRefresh(reload);
  const tasks = data ?? EMPTY_TASKS;
  const text = query.trim().toLowerCase();
  const visible = tasks.filter((task) =>
    `${task.display_name} ${task.reg_name} ${task.task_id}`
      .toLowerCase()
      .includes(text),
  );
  const selected = initialResource
    ? tasks.find((task) => task.task_id === initialResource)
    : visible[0];
  useEffect(() => {
    onOptionsChange(
      tasks.map((task) => ({
        value: task.task_id,
        label: formatDate(task.started_at || task.created_at),
      })),
    );
  }, [tasks, onOptionsChange]);
  return (
    <section className="workspace-page research-page online-workbench operations-workbench">
      <div className="research-layout">
        <aside className="task-index rail-panel">
          <TaskIndexControls
            eyebrow={t("operations.runHistory")}
            title={t(page.titleKey)}
            count={tasks.length}
            loading={loading}
            query={query}
            onQuery={setQuery}
            searchLabel={t("operations.search")}
            refreshLabel={t("onlinePipeline.refresh")}
            onRefresh={() => void refreshAll()}
          />
          <div className="rail-scroll">
            {loading && !data ? (
              <span className="task-loading">
                <LoaderCircle className="spin" />
              </span>
            ) : (
              data && (
                <OperationIndex
                  tasks={visible}
                  selected={selected?.task_id}
                  onSelected={onSelected}
                />
              )
            )}
            {data && !visible.length && (
              <p className="operation-index-empty">{t("operations.empty")}</p>
            )}
          </div>
        </aside>
        <RailResizer min={180} max={460} className="context-resizer" />
        <main className="research-canvas">
          {error && (
            <div className="error-state" role="alert">
              {error}
              <button onClick={() => void reload()}>{t("retry")}</button>
            </div>
          )}
          {selected &&
            (page.view === "pipeline" ? (
              <PipelineReport
                key={`${target}:${selected.task_id}:${selected.started_at}`}
                task={selected}
                target={target}
                onOpenTask={onOpenTask}
              />
            ) : (
              <TaskReport
                key={`${target}:${selected.task_id}:${selected.started_at}`}
                task={selected}
                target={target}
                onOpenTask={onOpenTask}
              />
            ))}
          {!selected && (
            <div className="empty-research">
              <Activity />
              <strong>
                {loading ? t("shell.loading") : t("operations.empty")}
              </strong>
            </div>
          )}
        </main>
      </div>
    </section>
  );
}
