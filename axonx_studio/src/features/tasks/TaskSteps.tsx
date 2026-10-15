import { useTranslation } from "react-i18next";
import type { TaskStepStatus } from "./types";

export function TaskSteps({
  steps,
  compact = false,
}: {
  steps: TaskStepStatus[];
  compact?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const stamp = (value: string | null | undefined) =>
    value
      ? new Date(value).toLocaleString(
          i18n?.resolvedLanguage === "zh" ? "zh-CN" : "en-US",
          {
            timeZone: "Asia/Shanghai",
            hour12: false,
          },
        )
      : "—";
  return (
    <div className={`pipeline-steps${compact ? " pipeline-stages" : ""}`}>
      {steps.map((step) => (
        <section
          className={`pipeline-step step-${step.state}`}
          key={`${step.parent}:${step.name}`}
        >
          <header>
            <strong>
              {t(
                `onlinePipeline.phases.${step.label || step.name}`,
                step.label || step.name,
              )}
            </strong>
            <span className={`online-status status-${step.state}`}>
              {t(
                `onlinePipeline.status.${step.state}`,
                step.state || "pending",
              )}
            </span>
          </header>
          <div className="pipeline-step-meta">
            {step.phase && (
              <span>
                {t(`onlinePipeline.phases.${step.phase}`, step.phase)}
              </span>
            )}
            {step.completed != null && (
              <span>
                {step.completed.toLocaleString()} /{" "}
                {step.total?.toLocaleString() ?? "—"}{" "}
                {t(`onlinePipeline.units.${step.unit}`, step.unit || "")}
              </span>
            )}
            {typeof step.metrics?.coverage === "number" && (
              <span>
                {t("onlinePipeline.coverage")}:{" "}
                {(step.metrics?.coverage * 100).toFixed(1)}%
              </span>
            )}
          </div>
          {step.total != null && step.total > 0 && step.completed != null && (
            <progress max={step.total} value={step.completed} />
          )}
          <div className="pipeline-step-meta">
            {step.scheduled_at && (
              <small>
                {t("onlinePipeline.scheduled")}: {stamp(step.scheduled_at)}
              </small>
            )}
            {step.deadline && (
              <small>
                {t("onlinePipeline.deadline")}: {stamp(step.deadline)}
              </small>
            )}
            {["pending", "waiting", "running"].includes(
              step.state || "pending",
            ) &&
              step.deadline && (
                <small>
                  {t("onlinePipeline.remaining", {
                    seconds: Math.max(
                      0,
                      Math.ceil(
                        (Date.parse(step.deadline) - Date.now()) / 1000,
                      ),
                    ),
                  })}
                </small>
              )}
            {step.updated_at && (
              <small>
                {t("onlinePipeline.updated")}: {stamp(step.updated_at)}
              </small>
            )}
          </div>
          {Object.keys(step.files || {}).length > 0 && (
            <details>
              <summary>
                {t("onlinePipeline.files")} ·{" "}
                {Object.keys(step.files || {}).length}
              </summary>
              <ul>
                {Object.entries(step.files || {}).map(([role, path]) => (
                  <li key={role}>
                    <small>{role}</small> <code>{path}</code>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {step.error && (
            <p className="online-reason">
              {t(`onlinePipeline.reasons.${step.error}`, step.error)}
            </p>
          )}
        </section>
      ))}
    </div>
  );
}
