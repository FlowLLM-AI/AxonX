import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { getTaskStatus } from "../tasks/api";
import { TaskSteps } from "../tasks/TaskSteps";
import { TaskChildren } from "../tasks/TaskChildren";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { Status } from "../tasks/TaskRow";
import { readTaskChildren } from "../tasks/tree";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { usePolling } from "../../shared/hooks/usePolling";

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
        replaced: t("onlinePipeline.replacedRun"),
        snapshot: t("onlinePipeline.changedSnapshot"),
      });
      return { parent, nodes };
    },
    [task.task_id, task.run_id, target, t],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  const refresh = useCallback(async () => {
    await reload();
  }, [reload]);
  usePolling(refresh, true);
  if (!data)
    return (
      <div className="empty-research">
        <p role={error ? "alert" : "status"}>
          {error || (loading ? t("shell.loading") : t("operations.empty"))}
        </p>
        <button onClick={() => void reload()}>{t("retry")}</button>
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
        <div>
          <p className="eyebrow">{t("operations.dataProgress")}</p>
          <h2>{task.display_name || task.reg_name}</h2>
          <details className="pipeline-identity">
            <summary>{parent.task_id}</summary>
            <small>{parent.run_id}</small>
          </details>
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
      <TaskSteps steps={parent.steps} />
      <h3>{t("operations.children")}</h3>
      <TaskChildren
        showOutput
        records={parent.children}
        nodes={nodes}
        onOpenTask={onOpenTask}
      />
      <details>
        <summary>{t("operations.result")}</summary>
        <pre>{JSON.stringify(parent.output_params, null, 2)}</pre>
      </details>
      <h3>{t("taskDetail.logs")}</h3>
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
                  <option value={node.status.task_id} key={node.status.run_id}>
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
    </article>
  );
}
