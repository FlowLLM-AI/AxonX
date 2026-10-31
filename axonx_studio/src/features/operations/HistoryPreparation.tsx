import { ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "../../shared/api/contracts";
import type { TaskNode } from "../tasks/tree";
import { etlTaskRecords } from "./daily";
import { isRecord } from "../../shared/lib/values";
import { PipelineSteps } from "./PipelineSteps";

/** Show workflow preparation progress alongside its exact ETL executions. */
export function HistoryPreparation({
  parent,
  nodes,
  target,
  onOpenTask,
  modelName,
  slot,
}: {
  parent: TaskMetadata;
  nodes: TaskNode[];
  target?: string;
  onOpenTask: (id: string) => void;
  modelName?: string;
  slot?: string;
}) {
  const { t, i18n } = useTranslation();
  const steps = parent.steps.filter((step) => step.group === "history");
  const outcomes = isRecord(parent.output_params.models)
    ? parent.output_params.models
    : {};
  const historyIds = new Map(
    Object.entries(outcomes).flatMap(([time, models]) =>
      isRecord(models)
        ? Object.entries(models).map(([name, result]): [string, string] => [
            `${name}-${time}`,
            isRecord(result) && isRecord(result.stages)
              ? String(result.stages.etl || "")
              : "",
          ])
        : [],
    ),
  );
  const rows = steps.map((step) => {
    const name = step.name.replace(/^history:/, "");
    return { name, step, records: etlTaskRecords(parent, name) };
  });
  return (
    <div className="pipeline-steps history-preparation">
      {rows
        .filter((entry) =>
          slot
            ? entry.name === `${modelName}-${slot}`
            : !modelName || entry.name.startsWith(`${modelName}-`),
        )
        .map(({ name, step, records }) => {
          const children = records.map((record) => ({
            record,
            node: nodes.find(
              (node) =>
                node.record.child_task_id === record.child_task_id &&
                node.record.started_at === record.started_at,
            ),
          }));
          const state = step.state || "pending";
          const details = children.flatMap(({ node }) => {
            const child = node?.status;
            if (!child) return [];
            const childSteps = child.steps.filter(
              (stage) =>
                stage.parent &&
                (!slot ||
                  !(
                    ["done", "succeeded"].includes(stage.state || "") &&
                    !stage.error &&
                    !Object.keys(stage.files || {}).length &&
                    !Object.keys(stage.metrics || {}).length &&
                    (stage.completed == null || stage.total === 1)
                  )),
            );
            return childSteps.length ? [{ child, steps: childSteps }] : [];
          });
          const errors = [
            ...new Set(
              [
                step.error,
                ...children.flatMap(({ record, node }) => [
                  record.error,
                  node?.error,
                  node?.status?.error,
                ]),
              ].filter(
                (error) =>
                  error &&
                  !details.some(({ steps }) =>
                    steps.some((stage) => stage.error === error),
                  ),
              ),
            ),
          ];
          const taskIds = records.flatMap((record) =>
            record.child_task_id ? [record.child_task_id] : [],
          );
          const reusedId = historyIds.get(name);
          if (!records.length && reusedId) taskIds.push(reusedId);
          const badge = (
            <span className={`online-status status-${state}`}>
              {t(`onlinePipeline.status.${state}`, state)}
            </span>
          );
          return (
            <section
              key={name}
              className={`pipeline-step history-preparation-card${slot ? " history-preparation-compact" : ""} step-${state}`}
            >
              <header>
                <strong>
                  {slot ? t("onlineWorkbench.historyInputs") : name}
                </strong>
                {slot && badge}
                {step.phase && (
                  <span className="history-preparation-note">
                    {t(`onlinePipeline.phases.${step.phase}`, step.phase)}
                  </span>
                )}
                <div className="history-preparation-actions">
                  {!slot && badge}
                  {taskIds.map((taskId) => (
                    <button
                      key={taskId}
                      type="button"
                      className="secondary-button"
                      title={t("onlinePipeline.openTask")}
                      aria-label={t("onlinePipeline.openTask")}
                      onClick={() => onOpenTask(taskId)}
                    >
                      <ArrowUpRight aria-hidden="true" />
                    </button>
                  ))}
                </div>
              </header>
              {step?.updated_at && !slot && (
                <small>
                  {t("onlinePipeline.updated")}:{" "}
                  {new Date(step.updated_at).toLocaleString(
                    i18n?.resolvedLanguage === "zh" ? "zh-CN" : "en-US",
                    { timeZone: "Asia/Shanghai", hour12: false },
                  )}
                </small>
              )}
              {errors.map((error) => (
                <p className="error-state" key={error}>
                  {error}
                </p>
              ))}
              {details.map(({ child, steps }) => (
                <div
                  className="history-preparation-stages"
                  key={`${child.task_id}:${child.started_at}`}
                >
                  <PipelineSteps
                    task={child}
                    target={target}
                    compact
                    steps={steps}
                  />
                </div>
              ))}
            </section>
          );
        })}
    </div>
  );
}
