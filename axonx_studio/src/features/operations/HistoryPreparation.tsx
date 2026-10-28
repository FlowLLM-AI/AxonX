import { ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "../../shared/api/contracts";
import type { TaskNode } from "../tasks/tree";
import { historyTaskRecords } from "./daily";
import { PipelineSteps } from "./PipelineSteps";

/** Join parent progress and its exact child Task into one card per model. */
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
  const records = historyTaskRecords(parent);
  const steps = parent.steps.filter((step) => step.group === "history");
  const rows = steps.map((step) => {
    const name = step.name.replace(/^history:/, "");
    return {
      name,
      step,
      record: records.find(
        (record) => record.node_name === `${name}-${record.reg_name}`,
      ),
    };
  });
  const unmatched = records.filter(
    (record) => !rows.some((row) => row.record === record),
  );
  const entries = [
    ...rows,
    ...unmatched.map((record) => ({
      name: record.node_name.endsWith(`-${record.reg_name}`)
        ? record.node_name.slice(0, -(record.reg_name.length + 1))
        : record.node_name,
      step: undefined,
      record,
    })),
  ];
  return (
    <div className="pipeline-steps history-preparation">
      {entries
        .filter((entry) =>
          slot
            ? entry.name === `${modelName}-${slot}`
            : !modelName || entry.name.startsWith(`${modelName}-`),
        )
        .map(({ name, step, record }) => {
          const node =
            record &&
            nodes.find(
              (node) =>
                node.record.child_task_id === record.child_task_id &&
                node.record.started_at === record.started_at,
            );
          const child = node?.status;
          const state =
            step?.state === "failed"
              ? "failed"
              : record?.state || step?.state || "pending";
          const errors = [
            ...new Set(
              [step?.error, record?.error, node?.error, child?.error].filter(
                Boolean,
              ),
            ),
          ];
          const childSteps = child?.steps.filter((stage) => stage.parent) || [];
          const summarized = slot
            ? childSteps.filter(
                (stage) =>
                  ["done", "succeeded"].includes(stage.state || "") &&
                  !stage.error &&
                  !Object.keys(stage.files || {}).length &&
                  !Object.keys(stage.metrics || {}).length &&
                  (stage.completed == null || stage.total === 1),
              )
            : [];
          const notes = [
            ...new Set(summarized.map((stage) => stage.phase).filter(Boolean)),
          ];
          const remaining = childSteps.filter(
            (stage) => !summarized.includes(stage),
          );
          const badge = (
            <span className={`online-status status-${state}`}>
              {t(`onlinePipeline.status.${state}`, state)}
            </span>
          );
          return (
            <section
              key={name}
              className={`pipeline-step history-preparation-card${slot ? " history-preparation-compact" : ""} step-${state === "succeeded" ? "done" : state}`}
            >
              <header>
                <strong>
                  {slot ? t("onlineWorkbench.historyInputs") : name}
                </strong>
                {slot && badge}
                {notes.map((phase) => (
                  <span className="history-preparation-note" key={phase}>
                    {t(`onlinePipeline.phases.${phase}`, phase || "")}
                  </span>
                ))}
                <div className="history-preparation-actions">
                  {!slot && badge}
                  {record?.child_task_id && (
                    <button
                      type="button"
                      className="secondary-button"
                      title={t("onlinePipeline.openTask")}
                      aria-label={t("onlinePipeline.openTask")}
                      onClick={() => onOpenTask(record.child_task_id!)}
                    >
                      <ArrowUpRight aria-hidden="true" />
                    </button>
                  )}
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
              {child && remaining.length > 0 && (
                <div className="history-preparation-stages">
                  <PipelineSteps
                    task={child}
                    target={target}
                    compact
                    steps={remaining}
                  />
                </div>
              )}
            </section>
          );
        })}
    </div>
  );
}
