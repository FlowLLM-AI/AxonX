import { useCallback, useEffect, useState } from "react";
import { Activity, LoaderCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { StudioPage } from "../../shared/api/contracts";
import type { TaskSummary } from "../tasks/types";
import { listSchedules, listTaskStatuses } from "../tasks/api";
import { formatDate } from "../tasks/format";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { usePolling } from "../../shared/hooks/usePolling";
import { RailResizer } from "../../shared/ui/RailResizer";
import { RunIndexControls } from "../../shared/ui/RunIndexControls";
import { PipelineReport } from "../online/PipelineReport";
import { TaskRunReport } from "./TaskRunReport";
import { ScheduleReport, ScheduleRunReport } from "./ScheduleReport";
import { OperationTree } from "./OperationTree";
import { buildOperationTree, searchOperationTree, runDate } from "./tree";
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
  const tree = buildOperationTree(page.schedules, schedules, tasks);
  const visible = searchOperationTree(tree, query);
  const runs = [...tree.groups.flatMap((group) => group.runs), ...tree.manual];
  const visibleRuns = [
    ...visible.groups.flatMap((group) => group.runs),
    ...visible.manual,
  ];
  const selected = initialResource
    ? runs.find((run) => run.id === initialResource)
    : page.view !== "schedules"
      ? visibleRuns.find((run) => run.kind === "task") || visibleRuns[0]
      : undefined;
  const selectedGroup = initialResource
    ? tree.groups.find((group) => group.id === initialResource)
    : !selected
      ? visible.groups[0]
      : undefined;
  const selectedTask = selected?.kind === "task" ? selected.task : undefined;
  const selectedJob = selected?.kind === "job" ? selected.run : undefined;
  const title = page.title[i18n?.resolvedLanguage === "zh" ? "zh" : "en"];
  useEffect(() => {
    const index = buildOperationTree(
      page.schedules,
      data?.schedules || [],
      data?.tasks || [],
    );
    onOptionsChange([
      ...index.groups.map((group) => ({ value: group.id, label: group.name })),
      ...[...index.groups.flatMap((group) => group.runs), ...index.manual].map(
        (run) => ({ value: run.id, label: formatDate(runDate(run)) }),
      ),
    ]);
  }, [data, page.schedules, onOptionsChange]);
  return (
    <section className="workspace-page research-page online-workbench operations-workbench">
      <div className="research-layout">
        <aside className="run-index rail-panel">
          <RunIndexControls
            eyebrow={t("operations.runHistory")}
            title={title}
            count={runs.length}
            loading={loading}
            query={query}
            onQuery={setQuery}
            searchLabel={t("operations.search")}
            refreshLabel={t("onlinePipeline.refresh")}
            onRefresh={() => void reload()}
          />
          <div className="rail-scroll">
            {loading && !data ? (
              <span className="run-loading">
                <LoaderCircle className="spin" />
              </span>
            ) : (
              data && (
                <OperationTree
                  groups={visible.groups}
                  manual={visible.manual}
                  showManual={page.view !== "schedules"}
                  selected={selected?.id || selectedGroup?.id}
                  onSelected={onSelected}
                />
              )
            )}
            {data &&
              query &&
              !visible.groups.length &&
              !visible.manual.length && (
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
          {data && selectedGroup && (
            <ScheduleReport
              name={selectedGroup.name}
              schedule={selectedGroup.schedule}
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
              />
            ) : (
              <TaskRunReport
                key={`${target}:${selectedTask.task_id}:${selectedTask.run_id}`}
                task={selectedTask}
                target={target}
                onOpenTask={onOpenTask}
              />
            ))}
          {!selected && !selectedGroup && (
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
