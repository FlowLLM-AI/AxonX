import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "../../shared/api/contracts";

export function DataUpdateProgress({ task }: { task: TaskMetadata }) {
  const { t } = useTranslation();
  const steps = task.steps.filter(
    (step) =>
      step.completed != null ||
      step.error ||
      typeof step.metrics?.coverage === "number",
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
  if (!rows.length) return null;
  return (
    <div className="online-table-card">
      <div className="online-table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("operations.step")}</th>
              <th>{t("quality.columns.result")}</th>
              <th>{t("operations.progress")}</th>
              <th>{t("quality.columns.description")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td>{row.name}</td>
                <td>
                  <span className={`online-status status-${row.state}`}>
                    {row.result}
                  </span>
                </td>
                <td>{row.progress}</td>
                <td>{row.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
