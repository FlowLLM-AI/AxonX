import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { StudioPage } from "../../shared/api/contracts";
import type { TaskSummary } from "../tasks/types";
import { listSchedules, listTaskStatuses } from "../tasks/api";
import { formatDate } from "../tasks/format";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { RailResizer } from "../../shared/ui/RailResizer";
import { RunIndexControls } from "../../shared/ui/RunIndexControls";
import { PipelineReport } from "../online/PipelineReport";
import { TaskRunReport } from "./TaskRunReport";
import {
  ScheduleDetails,
  ScheduleReport,
  ScheduleRunReport,
} from "./ScheduleReport";
import { OperationIndex } from "./OperationIndex";
import {
  buildOperationIndex,
  searchOperationIndex,
  findOperationEntry,
  entryDate,
  entryLabel,
} from "./model";
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
          Promise.all(
            page.schedules.map((name) => listSchedules(target, signal, name)),
          ).then((groups) => groups.flat()),
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
  const refreshAll = useRefresh(reload);
  const schedules = data?.schedules || [];
  const entries = useMemo(
    () =>
      data
        ? buildOperationIndex(page.schedules, data.schedules, data.tasks)
        : [],
    [data, page.schedules],
  );
  const visible = searchOperationIndex(entries, query);
  const selected = initialResource
    ? findOperationEntry(entries, schedules, initialResource)
    : page.view !== "schedules"
      ? visible.find((entry) => entry.kind === "task") || visible[0]
      : visible[0];
  const selectedTask = selected?.kind === "task" ? selected.task : undefined;
  const selectedJob = selected?.kind === "job" ? selected.run : undefined;
  const embeddedSchedule =
    selectedTask?.report_kind === "online_pipeline" && page.view === "pipeline";
  const scheduleResource =
    initialResource && selected && initialResource !== selected.id
      ? initialResource
      : undefined;
  const title = page.title[i18n?.resolvedLanguage === "zh" ? "zh" : "en"];
  useEffect(() => {
    onOptionsChange(
      entries.map((entry) => ({
        value: entry.id,
        label:
          entry.kind === "schedule"
            ? entryLabel(entry)
            : formatDate(entryDate(entry)),
      })),
    );
  }, [entries, onOptionsChange]);
  return (
    <section className="workspace-page research-page online-workbench operations-workbench">
      <div className="research-layout">
        <aside className="run-index rail-panel">
          <RunIndexControls
            eyebrow={t("operations.runHistory")}
            title={title}
            count={entries.length}
            loading={loading}
            query={query}
            onQuery={setQuery}
            searchLabel={t("operations.search")}
            refreshLabel={t("onlinePipeline.refresh")}
            onRefresh={() => void refreshAll()}
          />
          <div className="rail-scroll">
            {schedules.some(
              (schedule) =>
                schedule.job !== "submit" &&
                (schedule.history_total ?? 0) > (schedule.history?.length ?? 0),
            ) && (
              <p className="muted" role="status">
                {t("operations.historyLimited", { limit: 200 })}
              </p>
            )}
            {loading && !data ? (
              <span className="run-loading">
                <LoaderCircle className="spin" />
              </span>
            ) : (
              data && (
                <OperationIndex
                  entries={visible}
                  selected={selected?.id}
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
          {selected?.kind === "schedule" && (
            <ScheduleReport
              name={selected.name}
              schedule={selected.schedules[0] || null}
            />
          )}
          {selected &&
            selected.kind !== "schedule" &&
            !embeddedSchedule &&
            selected.schedules.length > 0 && (
              <ScheduleDetails
                key={`${target}:${selected.id}:${scheduleResource || ""}`}
                schedules={selected.schedules}
                defaultOpen={!!scheduleResource}
              />
            )}
          {selectedJob && <ScheduleRunReport run={selectedJob} />}
          {selectedTask &&
            (page.view === "pipeline" ? (
              <PipelineReport
                key={`${target}:${selectedTask.task_id}:${selectedTask.run_id}`}
                task={selectedTask}
                target={target}
                onOpenTask={onOpenTask}
                schedules={selected?.schedules}
                scheduleResource={scheduleResource}
              />
            ) : (
              <TaskRunReport
                key={`${target}:${selectedTask.task_id}:${selectedTask.run_id}`}
                task={selectedTask}
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
