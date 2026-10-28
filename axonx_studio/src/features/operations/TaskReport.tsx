import { Database } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { formatDateTime as formatDate } from "../../shared/lib/format";
import { selectOptions } from "../../shared/lib/values";
import { ReportTabs } from "../../shared/ui/ReportTabs";
import { Picker } from "../../shared/ui/Select";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { Status } from "../tasks/TaskRow";
import { getTaskStatus } from "../tasks/api";
import type { TaskReference } from "../tasks/model";
import { readTaskChildren, type TaskNode } from "../tasks/tree";
import { DataUpdateProgress } from "./DataUpdateProgress";
import { PipelineReport } from "./PipelineReport";

export function TaskReport({
  task,
  target,
  onOpenTask,
}: {
  task: TaskReference;
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [selectedTask, setSelectedTask] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      const parent = await getTaskStatus(task.task_id, { target, signal });
      if (parent.started_at !== task.started_at)
        throw new Error(t("onlinePipeline.restartedTask"));
      const nodes = await readTaskChildren(parent, target, signal, {
        replaced: t("onlinePipeline.replacedChild"),
        snapshot: t("onlinePipeline.changedSnapshot"),
      });
      return { parent, nodes };
    },
    [task.task_id, task.started_at, target, t],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  const refreshAll = useRefresh(reload);
  if (!data)
    return (
      <div className="empty-research">
        <p role={error ? "alert" : "status"}>
          {error || (loading ? t("shell.loading") : t("operations.empty"))}
        </p>
        <button onClick={() => void refreshAll()}>{t("retry")}</button>
      </div>
    );
  const { parent, nodes } = data;
  const children = new Map<string, TaskNode>();
  for (const node of nodes) {
    const id = node.record.child_task_id!;
    if (!children.has(id) || node.status) children.set(id, node);
  }
  const selected = children.get(selectedTask);
  const active = selectedTask ? selected?.status : parent;
  const activeError = selectedTask
    ? selected?.error || selected?.record.error || active?.error
    : "";
  const reportError = [
    error,
    parent.error,
    ...(selectedTask
      ? active
        ? [activeError]
        : []
      : nodes.map(
          (node) => node.error || node.record.error || node.status?.error,
        )),
  ]
    .filter(Boolean)
    .filter((message, index, all) => all.indexOf(message) === index)
    .join(" · ");
  const reports = (
    selectedTask
      ? active
        ? [active]
        : []
      : [parent, ...nodes.flatMap((node) => (node.status ? [node.status] : []))]
  ).filter(
    (report) =>
      selectedTask ||
      report.task_id !== parent.task_id ||
      !nodes.length ||
      Object.keys(report.output_params).some(
        (key) =>
          !["artifacts", "started_at", "task_id", "status", "flow"].includes(
            key,
          ),
      ),
  );
  const interfaces = [
    ...new Set(
      reports.flatMap((report) => {
        const apis = report.output_params.selected_apis;
        return Array.isArray(apis)
          ? apis.filter((api): api is string => typeof api === "string")
          : [];
      }),
    ),
  ];
  const unavailable = (
    <p className="error-state" role="alert">
      {activeError || t("onlinePipeline.replacedChild")}
    </p>
  );
  return (
    <article className="online-report data-update-report">
      <ReplicaNotice replica={parent.replica} state={parent.state} />
      <header>
        <span className="operation-detail-icon">
          <Database aria-hidden="true" />
        </span>
        <div>
          <p className="eyebrow">{t("operations.dataUpdate")}</p>
          <h2>{task.display_name || task.reg_name}</h2>
          <p className="operation-task-time">
            {t("operations.triggered")} ·{" "}
            {formatDate(parent.started_at || parent.created_at)}
          </p>
        </div>
        <Status state={parent.state} />
        <button
          className="secondary-button"
          disabled={!active}
          onClick={() => active && onOpenTask(active.task_id)}
        >
          {t("onlinePipeline.openTask")}
        </button>
      </header>
      {reportError && (
        <p className="error-state" role="alert">
          {reportError}
        </p>
      )}
      <ReportTabs
        defaultTab="result"
        actions={
          <Picker
            label={t("taskDetail.task")}
            value={selectedTask}
            onChange={setSelectedTask}
            className="online-model-picker"
            options={selectOptions(
              [
                "",
                ...children.keys(),
                ...(selectedTask && !selected ? [selectedTask] : []),
              ],
              {
                "": t("onlinePipeline.chainLog"),
                ...Object.fromEntries(
                  [...children].map(([id, { record }]) => [
                    id,
                    record.node_name,
                  ]),
                ),
                ...(selectedTask && !selected
                  ? { [selectedTask]: t("onlinePipeline.replacedChild") }
                  : {}),
              },
            )}
          />
        }
        tabs={[
          {
            id: "interfaces",
            label: t("operations.dataInterfaces"),
            content: active ? (
              <>
                {interfaces.length > 0 ? (
                  <pre className="data-update-json">
                    {JSON.stringify(interfaces, null, 2)}
                  </pre>
                ) : (
                  <p className="operation-index-empty">
                    {t("operations.noInterfaces")}
                  </p>
                )}
                {reports.map((report) => (
                  <DataUpdateProgress
                    key={`${report.task_id}:${report.started_at}`}
                    task={report}
                  />
                ))}
              </>
            ) : (
              unavailable
            ),
          },
          {
            id: "result",
            label: t("operations.dataResults"),
            content: active ? (
              <div className="operation-download-results">
                {reports.length ? (
                  reports.map((report) => (
                    <section
                      className="operation-download-result"
                      key={`${report.task_id}:${report.started_at}`}
                    >
                      {reports.length > 1 && <h3>{report.reg_name}</h3>}
                      <pre className="data-update-json">
                        {JSON.stringify(
                          Object.fromEntries(
                            Object.entries(report.output_params).filter(
                              ([key]) => key !== "selected_apis",
                            ),
                          ),
                          null,
                          2,
                        )}
                      </pre>
                    </section>
                  ))
                ) : (
                  <p className="operation-index-empty">
                    {t("operations.noResult")}
                  </p>
                )}
              </div>
            ) : (
              unavailable
            ),
          },
          {
            id: "logs",
            label: t("taskDetail.logs"),
            lazy: true,
            content: active ? (
              <TaskLogPanel
                key={`${target}:${active.task_id}:${active.started_at}`}
                task={active}
                target={target}
              />
            ) : (
              unavailable
            ),
          },
        ]}
      />
    </article>
  );
}

export function ReportView({
  task,
  target,
  onOpenTask,
}: {
  task: TaskReference & { report_kind: string | null };
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  return ["online", "online_pipeline", "compare_pipeline"].includes(
    task.report_kind || "",
  ) ? (
    <PipelineReport task={task} target={target} onOpenTask={onOpenTask} />
  ) : (
    <TaskReport task={task} target={target} onOpenTask={onOpenTask} />
  );
}
