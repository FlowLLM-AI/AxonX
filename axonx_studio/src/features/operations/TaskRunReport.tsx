import { Database } from "lucide-react";
import { ReportTabs } from "../../shared/ui/ReportTabs";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { getTaskStatus } from "../tasks/api";
import { DataUpdateProgress } from "./DataUpdateProgress";
import { OperationResult } from "./OperationResult";
import { TaskChildren } from "../tasks/TaskChildren";
import { ReportTable } from "../online/ReportTable";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import { readTaskChildren } from "../tasks/tree";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useRefresh } from "../../shared/hooks/useRefresh";

import type { TaskRunIdentity } from "../tasks/types";

export function TaskRunReport({
  task,
  target,
  onOpenTask,
}: {
  task: TaskRunIdentity;
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [logId, setLogId] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      const parent = await getTaskStatus(task.task_id, target, signal);
      if (parent.run_id !== task.run_id)
        throw new Error(t("onlinePipeline.replacedRun"));
      const nodes = await readTaskChildren(parent, target, signal, {
        replaced: t("onlinePipeline.replacedChildRun"),
        snapshot: t("onlinePipeline.changedSnapshot"),
      });
      return { parent, nodes };
    },
    [task.task_id, task.run_id, target, t],
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
  const logs = logId
    ? nodes.find((node) => node.status?.task_id === logId)?.status
    : parent;
  return (
    <article className="online-report">
      <ReplicaNotice replica={parent.replica} state={parent.state} />
      <header>
        <span className="operation-detail-icon">
          <Database aria-hidden="true" />
        </span>
        <div>
          <p className="eyebrow">{t("operations.dataUpdate")}</p>
          <h2>{task.display_name || task.reg_name}</h2>
          <p className="operation-run-time">
            {t("operations.triggered")} ·{" "}
            {formatDate(parent.started_at || parent.created_at)}
          </p>
        </div>
        <Status state={parent.state} />
        <button
          className="secondary-button"
          onClick={() => onOpenTask(parent.task_id)}
        >
          {t("onlinePipeline.openTask")}
        </button>
      </header>
      {(error || parent.error) && (
        <p className="error-state" role="alert">
          {error || parent.error}
        </p>
      )}
      <ReportTabs
        defaultTab={
          ["running", "pending", "queued"].includes(parent.state)
            ? "progress"
            : "result"
        }
        tabs={[
          {
            id: "progress",
            label: t("operations.dataProgress"),
            content: (
              <>
                <DataUpdateProgress task={parent} target={target} />
              </>
            ),
          },
          ...(parent.children.length
            ? [
                {
                  id: "children",
                  label: t("operations.children"),
                  content: (
                    <>
                      <ReportTable
                        rows={nodes.map((node) => ({
                          name: String(
                            node.status?.input_params.task_name ||
                              node.record.node_name,
                          ),
                          result: node.error
                            ? t("operations.unavailableRecord")
                            : t(
                                `states.${node.record.state}`,
                                node.record.state,
                              ),
                          description: node.error || node.record.error || "—",
                          taskId: node.status?.task_id,
                        }))}
                        columns={[
                          { key: "name", label: t("operations.step") },
                          { key: "result", label: t("quality.columns.result") },
                          {
                            key: "description",
                            label: t("quality.columns.description"),
                          },
                          {
                            key: "taskId",
                            label: t("operations.details"),
                            render: (row) =>
                              row.taskId ? (
                                <button
                                  className="secondary-button"
                                  onClick={() => onOpenTask(String(row.taskId))}
                                >
                                  {t("onlinePipeline.openTask")}
                                </button>
                              ) : (
                                "—"
                              ),
                          },
                        ]}
                      />
                      <details className="operation-result-details">
                        <summary>{t("operations.stageDetails")}</summary>
                        <TaskChildren
                          target={target}
                          records={parent.children}
                          nodes={nodes}
                          onOpenTask={onOpenTask}
                        />
                      </details>
                    </>
                  ),
                },
              ]
            : []),
          {
            id: "result",
            label: t("operations.result"),
            content: (
              <>
                <OperationResult value={parent.output_params} />
              </>
            ),
          },
          {
            id: "logs",
            label: t("taskDetail.logs"),
            content: (
              <>
                <label className="pipeline-log-source">
                  {t("onlinePipeline.logSource")}
                  <select
                    value={logId}
                    onChange={(event) => setLogId(event.target.value)}
                  >
                    <option value="">{t("onlinePipeline.chainLog")}</option>
                    {nodes.flatMap((node) =>
                      node.status
                        ? [
                            <option
                              value={node.status.task_id}
                              key={node.status.run_id}
                            >
                              {node.status.reg_name}
                            </option>,
                          ]
                        : [],
                    )}
                  </select>
                </label>
                {logs ? (
                  <TaskLogPanel
                    key={`${logs.task_id}:${logs.run_id}`}
                    task={logs}
                    target={target}
                  />
                ) : (
                  <p>{t("onlinePipeline.replacedRun")}</p>
                )}
              </>
            ),
          },
        ]}
      />
    </article>
  );
}
