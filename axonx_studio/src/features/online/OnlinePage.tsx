import { useCallback, useState } from "react";
import { Activity, ArrowRight, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { listTaskStatuses } from "../tasks/api";
import { Status } from "../tasks/TaskRow";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { usePolling } from "../../shared/hooks/usePolling";
import { RailResizer } from "../../shared/ui/RailResizer";
import { RunIndexControls } from "../../shared/ui/RunIndexControls";
import { playground } from "../../app/environment";
import { isOnlineTask } from "./types";
import { PipelineReport } from "./PipelineReport";

export default function OnlinePage({
  target,
  initialTaskId,
  onSelected,
  onConnection,
  onOpenTask,
}: {
  target?: string;
  initialTaskId?: string;
  onSelected: (id: string) => void;
  onConnection: (online: boolean) => void;
  onOpenTask: (id: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const tasks = await listTaskStatuses(target, signal);
        if (!signal.aborted) onConnection(true);
        return tasks
          .filter(isOnlineTask)
          .sort((a, b) =>
            (b.created_at || "").localeCompare(a.created_at || ""),
          );
      } catch (reason) {
        if (!signal.aborted) onConnection(false);
        throw reason;
      }
    },
    [target, onConnection],
  );
  const { data, loading, error, reload } = useAsyncResource(load);
  const refresh = useCallback(async () => {
    await reload();
  }, [reload]);
  usePolling(refresh, true);
  const tasks = (data || []).filter((task) =>
    ["online_pipeline", "compare_pipeline"].includes(task.report_kind || ""),
  );
  const visible = tasks.filter((task) =>
    `${task.task_id} ${task.display_name || task.reg_name}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const selected =
    data?.find((task) => task.task_id === initialTaskId) || visible[0];
  return (
    <section className="workspace-page research-page online-workbench">
      <div className="research-layout">
        <aside className="run-index rail-panel">
          <RunIndexControls
            title={t("research.task_versions")}
            count={tasks.length}
            loading={loading}
            query={query}
            onQuery={setQuery}
            searchLabel={t("research.search_task_id")}
            refreshLabel={t("onlinePipeline.refresh")}
            onRefresh={() => void reload()}
          />
          <div className="rail-scroll">
            {loading && !data ? (
              <span className="run-loading">
                <LoaderCircle className="spin" />
              </span>
            ) : (
              visible.map((task) => (
                <article
                  className={selected?.task_id === task.task_id ? "active" : ""}
                  key={task.task_id}
                >
                  <button
                    className="run-main rail-list-item"
                    aria-pressed={selected?.task_id === task.task_id}
                    onClick={() => onSelected(task.task_id)}
                  >
                    <span className="run-item-avatar rail-avatar">
                      <Activity />
                    </span>
                    <span className="rail-item-copy">
                      <strong>{task.display_name || task.reg_name}</strong>
                      <code>{task.task_id}</code>
                      <small>
                        {task.created_at
                          ? new Date(task.created_at).toLocaleString(
                              i18n?.resolvedLanguage === "zh"
                                ? "zh-CN"
                                : "en-US",
                            )
                          : "—"}
                      </small>
                      <Status state={task.state} />
                    </span>
                    <ArrowRight />
                  </button>
                </article>
              ))
            )}
          </div>
        </aside>
        <RailResizer min={180} max={460} className="context-resizer" />
        <main className="research-canvas">
          {playground && (
            <div className="online-demo">
              <Activity size={16} />
              {t("onlinePipeline.demo")}
            </div>
          )}
          {error && (
            <div className="error-state" role="alert">
              {error}
              <button onClick={() => void reload()}>{t("retry")}</button>
            </div>
          )}
          {selected ? (
            <PipelineReport
              key={`${target}:${selected.task_id}:${selected.run_id}`}
              task={selected}
              target={target}
              onOpenTask={onOpenTask}
            />
          ) : (
            <div className="empty-research">
              <Activity />
              <strong>
                {loading ? t("shell.loading") : t("onlinePipeline.empty")}
              </strong>
            </div>
          )}
        </main>
      </div>
    </section>
  );
}
