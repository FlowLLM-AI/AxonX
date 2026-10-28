import { Activity } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { Select } from "../../shared/ui/Select";
import { getTaskStatus } from "../tasks/api";
import type { TaskReference } from "../tasks/model";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { Status } from "../tasks/TaskRow";
import { readTaskChildren } from "../tasks/tree";
import { ComparePipeline } from "./ComparePipeline";
import { OnlineWorkbench } from "./OnlineWorkbench";
import { Outcome } from "./Outcome";
import { PipelineSteps } from "./PipelineSteps";
import { parseOnlineReport } from "./report";
import { StockReport } from "./StockReport";

export function PipelineReport({
  task,
  target,
  onOpenTask,
}: {
  task: TaskReference;
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [logId, setLogId] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      const parent = await getTaskStatus(task.task_id, { target, signal });
      if (parent.started_at !== task.started_at)
        throw new Error(t("onlinePipeline.restartedTask"));
      const nodes = await readTaskChildren(parent, target, signal, {
        replaced: t("onlinePipeline.replacedChild"),
        snapshot: t("onlinePipeline.changedSnapshot"),
      });
      const children = nodes.map((node) => {
        try {
          return {
            ...node,
            report:
              node.status?.report_kind === "online"
                ? parseOnlineReport(node.status.output_params).report
                : null,
          };
        } catch (reason) {
          return { ...node, report: null, error: String(reason) };
        }
      });
      return {
        parent,
        refreshedAt: new Date().toISOString(),
        children,
        output: parseOnlineReport(parent.output_params),
      };
    },
    [task.task_id, task.started_at, target, t],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  const refreshAll = useRefresh(reload);
  if (!data)
    return (
      <article className="online-report pipeline-report">
        <p role={error ? "alert" : "status"}>
          {error || (loading ? t("shell.loading") : t("onlinePipeline.empty"))}
        </p>
        <button onClick={() => void refreshAll()}>{t("retry")}</button>
      </article>
    );
  const { parent, children, output } = data;
  const pipeline = parent.report_kind === "online_pipeline";
  const compare = parent.report_kind === "compare_pipeline";
  const statuses = children.flatMap((item) =>
    item.status ? [item.status] : [],
  );
  const logs = logId
    ? statuses.find((child) => child.task_id === logId)
    : parent;
  const rows = output.windows || output.comparisons || [];
  const runtime = (
    <>
      <h3>
        {t(
          parent.task_type === "analysis"
            ? "onlinePipeline.comparisons"
            : "onlinePipeline.windows",
        )}
      </h3>
      {output.model_identity && (
        <div className="online-model">
          {Object.entries(output.model_identity).map(([key, value]) => (
            <span key={key}>
              <small>{key}</small>
              <code>{value}</code>
            </span>
          ))}
        </div>
      )}
      <PipelineSteps
        task={parent}
        target={target}
        steps={parent.steps.filter((step) => step.parent)}
      />
      {rows.map((row) => (
        <Outcome
          key={row.key}
          row={row}
          taskId={parent.task_id}
          target={target}
        />
      ))}
    </>
  );
  const logPanel = (
    <>
      <label className="pipeline-log-source">
        {t("onlinePipeline.logSource")}
        <Select
          value={logId}
          onChange={(event) => setLogId(event.target.value)}
        >
          <option value="">{t("onlinePipeline.chainLog")}</option>
          {statuses.map((child) => (
            <option key={child.task_id} value={child.task_id}>
              {child.reg_name} · {child.input_params.task_name as string}
            </option>
          ))}
        </Select>
      </label>
      {logs ? (
        <TaskLogPanel
          key={`${target}:${logs.task_id}:${logs.started_at}`}
          task={logs}
          target={target}
        />
      ) : (
        <p>{t("onlinePipeline.restartedTask")}</p>
      )}
    </>
  );
  if (compare)
    return (
      <ComparePipeline
        parent={parent}
        nodes={children}
        target={target}
        onOpenTask={onOpenTask}
        refreshedAt={data.refreshedAt}
        error={error}
      />
    );
  if (pipeline)
    return (
      <OnlineWorkbench
        parent={parent}
        refreshedAt={data.refreshedAt}
        error={error}
        nodes={children}
        target={target}
        onOpenTask={onOpenTask}
      />
    );
  return (
    <article className="online-report pipeline-report">
      <ReplicaNotice replica={parent.replica} state={parent.state} />
      <header>
        <span className="operation-detail-icon">
          <Activity aria-hidden="true" />
        </span>
        <div>
          <p className="eyebrow">
            {t(`onlinePipeline.kinds.${parent.task_type}`, parent.task_type)}
          </p>
          <h2>
            {String(
              parent.input_params.trade_date ??
                task.display_name ??
                task.reg_name,
            )}
          </h2>
          <div className="pipeline-identity" title={parent.started_at}>
            {parent.task_id}
          </div>
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
        <div className="error-state" role="alert">
          {error || parent.error}
          <button onClick={() => void refreshAll()}>{t("retry")}</button>
        </div>
      )}
      {output.report ? (
        <StockReport report={output.report} target={target} runtime={runtime} />
      ) : (
        !pipeline && !compare && runtime
      )}
      {children
        .filter((child) => child.error)
        .map((child, index) => (
          <p className="error-state" key={index}>
            {child.error}
          </p>
        ))}
      {!pipeline && !compare && logPanel}
    </article>
  );
}
