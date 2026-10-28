import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { parseHash, routeHash } from "../../app/routes";
import type { TaskMetadata } from "../../shared/api/contracts";
import type { TaskStepStatus } from "../../shared/api/event";
import { TaskQuality } from "./QualityReport";

export function PipelineSteps({
  steps,
  compact = false,
  task,
  target,
  filesOnly = false,
}: {
  steps: TaskStepStatus[];
  compact?: boolean;
  task?: TaskMetadata;
  target?: string;
  filesOnly?: boolean;
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
          {task && step.group === "collection" && !filesOnly ? (
            <TaskQuality
              windows={task.output_params.windows}
              windowKey={step.name.replace(/^collection:/, "")}
              taskId={task.task_id}
              target={target}
              files={
                Object.keys(step.files || {}).length ? (
                  <StepFiles files={step.files} />
                ) : undefined
              }
            />
          ) : (
            <StepFiles files={step.files} />
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

function StepFiles({ files }: { files?: Record<string, string> | null }) {
  const { t } = useTranslation();
  if (!Object.keys(files || {}).length) return null;
  return (
    <div className="pipeline-step-files">
      <div className="pipeline-files-heading">
        {t("onlinePipeline.files")}
        <span className="pipeline-file-count">
          {Object.keys(files || {}).length}
        </span>
      </div>
      <ul>
        {Object.entries(files || {}).map(([role, path]) => (
          <li key={role}>
            <a
              href={routeHash(parseHash(window.location.hash).machineId, {
                section: "workspace",
                view: "files",
                resource: path,
              })}
            >
              <FileText aria-hidden="true" />
              <span>{path.split(/[\\/]/).pop()}</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
