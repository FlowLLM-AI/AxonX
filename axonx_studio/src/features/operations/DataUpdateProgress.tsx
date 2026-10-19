import { useTranslation } from "react-i18next";
import { ReportTable } from "../online/ReportTable";
import { TaskSteps } from "../tasks/TaskSteps";
import type { TaskMetadata } from "../tasks/types";

export function DataUpdateProgress({
  task,
  target,
}: {
  task: TaskMetadata;
  target?: string;
}) {
  const { t } = useTranslation();
  const steps = task.steps.filter(
    (step) =>
      step.state !== "done" ||
      step.completed != null ||
      step.error ||
      Object.keys(step.files || {}).length > 0,
  );
  const rows = steps.map((step) => ({
    name: t(
      `onlinePipeline.phases.${step.label || step.name}`,
      step.label || step.name,
    ),
    state: step.state,
    result: t(
      `onlineWorkbench.states.${step.state}`,
      t(`onlinePipeline.status.${step.state}`, step.state),
    ),
    progress:
      step.completed != null
        ? `${step.completed.toLocaleString()} / ${step.total?.toLocaleString() ?? "—"} ${t(`onlinePipeline.units.${step.unit === "symbols" ? "stocks" : step.unit}`, step.unit || "")}`
        : "—",
    description:
      step.error ||
      [
        ...(step.phase
          ? [t(`onlinePipeline.phases.${step.phase}`, step.phase)]
          : []),
        ...(typeof step.metrics?.coverage === "number"
          ? [
              `${t("onlinePipeline.coverage")} ${(step.metrics.coverage * 100).toFixed(2)}%`,
            ]
          : []),
      ].join(" · ") ||
      "—",
  }));
  return (
    <>
      {rows.length ? (
        <ReportTable
          rows={rows}
          columns={[
            { key: "name", label: t("operations.step") },
            {
              key: "result",
              label: t("quality.columns.result"),
              render: (row) => (
                <span className={`online-status status-${row.state}`}>
                  {String(row.result)}
                </span>
              ),
            },
            { key: "progress", label: t("operations.progress") },
            { key: "description", label: t("quality.columns.description") },
          ]}
        />
      ) : (
        <p className="operation-index-empty">{t("operations.noProgress")}</p>
      )}
      {task.steps.length > 0 && (
        <details className="operation-result-details">
          <summary>{t("operations.stageDetails")}</summary>
          <TaskSteps task={task} target={target} steps={task.steps} />
        </details>
      )}
    </>
  );
}
