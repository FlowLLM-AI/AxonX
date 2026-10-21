import { useState } from "react";
import { Check, ChevronRight, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "./types";
import { formatDate } from "./format";

export function ExecutionSteps({ task }: { task: TaskMetadata }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const steps = task.steps;
  const failed = (index: number) =>
    steps[index].state === "failed" || steps[index].state === "missed";
  const done = (index: number) => steps[index].state === "done";
  const groups: number[][] = [];
  steps.forEach((step, index) => {
    const previous = groups.at(-1);
    if (
      previous &&
      done(index) &&
      done(index - 1) &&
      step.name === steps[index - 1].name &&
      step.parent === steps[index - 1].parent
    )
      previous.push(index);
    else groups.push([index]);
  });
  const row = (index: number) => {
    const step = steps[index];
    const percentage = Math.max(0, Math.min(100, step.percentage ?? 0));
    const active = step.state === "running";
    return (
      <div
        className={`step-item ${step.parent ? "step-substep" : ""} ${failed(index) ? "failed" : ""}`}
        key={index}
      >
        <span
          className={
            failed(index)
              ? "failed"
              : done(index)
                ? "done"
                : active
                  ? "active"
                  : undefined
          }
          style={
            active
              ? ({ "--step-progress": `${percentage}%` } as React.CSSProperties)
              : undefined
          }
        >
          {failed(index) ? <X /> : done(index) ? <Check /> : index + 1}
        </span>
        <div>
          <strong>{step.label || step.name}</strong>
          <small>
            {failed(index)
              ? step.error || task.error || t("error")
              : step.state === "skipped"
                ? t("onlinePipeline.status.skipped")
                : step.finished_at
                  ? formatDate(step.finished_at)
                  : step.started_at
                    ? `${Math.round(percentage)}%`
                    : t("notStarted")}
          </small>
        </div>
      </div>
    );
  };
  return (
    <div className="step-list">
      {groups.length ? (
        groups.map((indices) => {
          const start = indices[0];
          if (indices.length === 1) return row(start);
          const open = expanded.has(start);
          return (
            <div
              className={`repeated-steps ${steps[start].parent ? "step-substep" : ""}`}
              key={start}
            >
              <button
                className="step-item repeated-steps-toggle"
                aria-expanded={open}
                onClick={() =>
                  setExpanded((current) => {
                    const next = new Set(current);
                    if (next.has(start)) next.delete(start);
                    else next.add(start);
                    return next;
                  })
                }
              >
                <span className="done">
                  <Check />
                </span>
                <div>
                  <strong>{steps[start].label || steps[start].name}</strong>
                  <small>
                    {t("taskDetail.repeatedSteps", { count: indices.length })}
                  </small>
                </div>
                <ChevronRight className={open ? "expanded" : ""} />
              </button>
              {open && (
                <div className="repeated-steps-items">{indices.map(row)}</div>
              )}
            </div>
          );
        })
      ) : (
        <p className="muted">{t("notStarted")}</p>
      )}
    </div>
  );
}
