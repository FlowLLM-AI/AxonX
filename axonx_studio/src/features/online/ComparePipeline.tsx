import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "../tasks/types";
import { TaskSteps } from "../tasks/TaskSteps";
import { TaskChildren } from "../tasks/TaskChildren";
import type { TaskNode } from "../tasks/tree";
import { isRecord } from "../../shared/lib/values";
import { parseOnlineReport } from "./types";
import { Outcome } from "./Outcome";

export function ComparePipeline({
  parent,
  nodes,
  target,
  onOpenTask,
}: {
  parent: TaskMetadata;
  nodes: TaskNode[];
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const models = parent.input_params.models as {
    task_name: string;
    feature_provider: string;
  }[];
  const outcomes = isRecord(parent.output_params.models)
    ? parent.output_params.models
    : {};
  return (
    <>
      {parent.output_params.status === "market_closed" && (
        <p>{t("onlinePipeline.closed")}</p>
      )}
      <h3>{t("onlinePipeline.download")}</h3>
      <TaskSteps
        steps={parent.steps.filter((step) => step.group === "download")}
      />
      <TaskChildren
        records={parent.children.filter((child) =>
          nodes.some(
            (node) =>
              node.record.run_id === child.run_id &&
              node.status?.category === "data_update",
          ),
        )}
        nodes={nodes}
        onOpenTask={onOpenTask}
      />
      <h3>{t("onlinePipeline.modelStages")}</h3>
      {(models || []).map((model) => {
        const value = outcomes[model.task_name];
        const outcome = isRecord(value) ? value : {};
        const steps = parent.steps.filter(
          (step) => step.group === model.task_name,
        );
        const active = ["queued", "running"].includes(parent.state);
        const unfinished =
          !outcome.status ||
          ["pending", "waiting", "running"].includes(String(outcome.status));
        let state = String(outcome.status || "waiting");
        if (steps.some((step) => step.state === "failed")) state = "failed";
        else if (!active && unfinished)
          state = parent.state === "cancelled" ? "cancelled" : "skipped";
        else if (steps.some((step) => step.state === "running"))
          state = "running";
        const records = parent.children.filter(
          (child) =>
            child.node_name === `${model.task_name}-${child.task}` ||
            child.node_name ===
              `${model.task_name}-${parent.input_params.trade_time}-${child.task}`,
        );
        return (
          <section className="pipeline-model" key={model.task_name}>
            <header>
              <strong>
                {model.task_name} · {model.feature_provider}
              </strong>
              <span className={`online-status status-${state}`}>
                {t(`onlinePipeline.status.${state}`, state)}
              </span>
            </header>
            {typeof outcome.error === "string" && (
              <p className="error-state">{outcome.error}</p>
            )}
            <TaskSteps compact steps={steps} />
            {nodes
              .filter(
                (node) =>
                  node.status?.report_kind === "online" &&
                  Array.isArray(node.status.output_params.comparisons) &&
                  records.some(
                    (record) => record.run_id === node.status?.run_id,
                  ),
              )
              .map((node) => (
                <ComparisonResults
                  key={node.status!.run_id}
                  task={node.status!}
                  target={target}
                />
              ))}
            <TaskChildren
              records={records}
              nodes={nodes}
              onOpenTask={onOpenTask}
            />
          </section>
        );
      })}
    </>
  );
}

function ComparisonResults({
  task,
  target,
}: {
  task: TaskMetadata;
  target?: string;
}) {
  try {
    return (
      <>
        {(parseOnlineReport(task.output_params).comparisons || []).map(
          (row) => (
            <Outcome
              key={row.key}
              row={row}
              taskId={task.task_id}
              target={target}
            />
          ),
        )}
      </>
    );
  } catch (reason) {
    return <p className="error-state">{String(reason)}</p>;
  }
}
