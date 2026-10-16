import { useCallback, useEffect, useState } from "react";
import { Activity, ArrowRight, Clock, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { StudioPage } from "../../shared/api/contracts";
import type { TaskSummary } from "../tasks/types";
import { listSchedules, listTaskStatuses } from "../tasks/api";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { usePolling } from "../../shared/hooks/usePolling";
import { RailResizer } from "../../shared/ui/RailResizer";
import { RunIndexControls } from "../../shared/ui/RunIndexControls";
import { PipelineReport } from "../online/PipelineReport";
import { TaskRunReport } from "./TaskRunReport";
import { ScheduleReport } from "./ScheduleReport";
import type { ContextOption } from "../../app/types";

function matchesPage(task: TaskSummary, page: StudioPage) {
  return (
    page.category !== null &&
    task.category === page.category &&
    !task.parent_run_id
  );
}

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
        const [schedules, tasks] = await Promise.all([
          listSchedules(target, signal),
          page.view === "schedules"
            ? Promise.resolve([])
            : listTaskStatuses(target, signal),
        ]);
        signal.throwIfAborted();
        onConnection(true);
        return {
          schedules: schedules.filter((schedule) =>
            page.schedules.includes(schedule.name),
          ),
          tasks: tasks
            .filter((task) => matchesPage(task, page))
            .sort((a, b) =>
              (b.created_at || "").localeCompare(a.created_at || ""),
            ),
        };
      } catch (reason) {
        if (!signal.aborted) onConnection(false);
        throw reason;
      }
    },
    [target, page, onConnection],
  );
  const { data, loading, error, reload } = useAsyncResource(load);
  const refresh = useCallback(async () => {
    await reload();
  }, [reload]);
  usePolling(refresh, true);
  const tasks = data?.tasks || [];
  const schedules = data?.schedules || [];
  const visible = tasks.filter((task) =>
    `${task.task_id} ${task.display_name} ${task.source.schedule?.name || ""}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const scheduleId = initialResource?.startsWith("schedule:")
    ? initialResource.slice(9)
    : undefined;
  const selectedSchedule =
    scheduleId || (page.view === "schedules" ? page.schedules[0] : undefined);
  const schedule = schedules.find((item) => item.name === selectedSchedule);
  const scheduleTasks = selectedSchedule
    ? visible.filter((task) => task.source.schedule?.name === selectedSchedule)
    : visible;
  const selected =
    initialResource && !scheduleId
      ? tasks.find((task) => task.task_id === initialResource)
      : scheduleTasks[0];
  const title = page.title[i18n?.resolvedLanguage === "zh" ? "zh" : "en"];
  useEffect(() => {
    onOptionsChange([
      ...(data?.schedules || []).map((schedule) => ({
        value: `schedule:${schedule.name}`,
        label: schedule.name,
      })),
      ...(data?.tasks || []).map((task) => ({
        value: task.task_id,
        label: task.display_name || task.reg_name,
      })),
    ]);
  }, [data, onOptionsChange]);
  return (
    <section className="workspace-page research-page online-workbench">
      <div className="research-layout">
        <aside className="run-index rail-panel">
          <RunIndexControls
            eyebrow={page.view === "schedules" ? "JOB SCHEDULES" : "TASK RUNS"}
            title={title}
            count={page.view === "schedules" ? schedules.length : tasks.length}
            loading={loading}
            query={query}
            onQuery={setQuery}
            searchLabel={t("operations.search")}
            refreshLabel={t("onlinePipeline.refresh")}
            onRefresh={() => void reload()}
          />
          <div className="rail-scroll">
            {page.view !== "schedules" && (
              <button
                className="operation-all secondary-button"
                onClick={() => onSelected("")}
              >
                {t("operations.allRuns")}
              </button>
            )}
            {page.schedules
              .filter((name) =>
                name.toLowerCase().includes(query.toLowerCase()),
              )
              .map((name) => {
                const item = schedules.find(
                  (schedule) => schedule.name === name,
                );
                return (
                  <button
                    className={`operation-schedule rail-list-item${selectedSchedule === name ? " active" : ""}`}
                    key={name}
                    onClick={() => onSelected(`schedule:${name}`)}
                    aria-pressed={selectedSchedule === name}
                  >
                    <Clock />
                    <span className="rail-item-copy">
                      <strong>{name}</strong>
                      <small>{item ? item.cron : t("schedules.removed")}</small>
                      {item?.last_trigger && (
                        <Status state={item.last_trigger.state} />
                      )}
                    </span>
                  </button>
                );
              })}
            {loading && !data && (
              <span className="run-loading">
                <LoaderCircle className="spin" />
              </span>
            )}
            {scheduleTasks.map((task) => (
              <article
                key={task.task_id}
                className={selected?.task_id === task.task_id ? "active" : ""}
              >
                <button
                  className="run-main rail-list-item"
                  onClick={() => onSelected(task.task_id)}
                  aria-pressed={selected?.task_id === task.task_id}
                >
                  <span className="run-item-avatar rail-avatar">
                    <Activity />
                  </span>
                  <span className="rail-item-copy">
                    <strong>{task.display_name || task.reg_name}</strong>
                    <code>{task.task_id}</code>
                    <small>{formatDate(task.created_at)}</small>
                    <small>
                      {task.source.schedule
                        ? t("schedules.scheduledSource", {
                            name: task.source.schedule.name,
                          })
                        : t(`schedules.sources.${task.source.kind}`)}
                    </small>
                    <Status state={task.state} />
                  </span>
                  <ArrowRight />
                </button>
              </article>
            ))}
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
          {data && selectedSchedule && (
            <ScheduleReport
              name={selectedSchedule}
              schedule={schedule || null}
            />
          )}
          {selected ? (
            page.view === "pipeline" ? (
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
            )
          ) : (
            (page.view !== "schedules" || !selectedSchedule) && (
              <div className="empty-research">
                <Activity />
                <strong>
                  {loading ? t("shell.loading") : t("operations.empty")}
                </strong>
              </div>
            )
          )}
        </main>
      </div>
    </section>
  );
}
