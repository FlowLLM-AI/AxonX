import { useCallback, useEffect, useState } from "react";
import { Activity, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { StudioPage } from "../../shared/api/contracts";
import type { TaskSummary } from "../tasks/types";
import { listTaskStatuses } from "../tasks/api";
import { formatDate } from "../tasks/format";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { RailResizer } from "../../shared/ui/RailResizer";
import { RunIndexControls } from "../../shared/ui/RunIndexControls";
import { PipelineReport } from "../online/PipelineReport";
import { TaskRunReport } from "./TaskRunReport";
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
  page: StudioPage;
  target?: string;
  initialResource?: string;
  onSelected: (id: string) => void;
  onOptionsChange: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
  onOpenTask: (id: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const tasks = await listTaskStatuses(target, signal);
        signal.throwIfAborted();
        onConnection(true);
        return tasks
          .filter(
            (task) => task.category === page.category && !task.parent_run_id,
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
  const title = page.title[i18n?.resolvedLanguage === "zh" ? "zh" : "en"];
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
        <aside className="run-index rail-panel">
          <RunIndexControls
            eyebrow={t("operations.runHistory")}
            title={title}
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
              <span className="run-loading">
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
                key={`${target}:${selected.task_id}:${selected.run_id}`}
                task={selected}
                target={target}
                onOpenTask={onOpenTask}
              />
            ) : (
              <TaskRunReport
                key={`${target}:${selected.task_id}:${selected.run_id}`}
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
