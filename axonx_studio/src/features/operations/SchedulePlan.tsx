import { AlertTriangle, CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Schedule } from "../tasks/types";
import { isEarlierSubmission, type ScheduleTask } from "./model";

export function SchedulePlanButton({
  schedules,
  task,
  open,
  onToggle,
  panelId,
}: {
  schedules: Schedule[];
  task?: ScheduleTask;
  open: boolean;
  onToggle: () => void;
  panelId: string;
}) {
  const { t } = useTranslation();
  const failed = schedules.find(
    (schedule) =>
      schedule.last_trigger?.state === "failed" &&
      !isEarlierSubmission(schedule, task),
  );
  const warning = failed
    ? t(
        failed.job === "submit"
          ? "operations.lastSubmissionFailed"
          : "operations.plan.triggerFailed",
      )
    : "";
  return (
    <button
      type="button"
      className="secondary-button schedule-plan-toggle"
      aria-expanded={open}
      aria-controls={panelId}
      aria-label={`${t("operations.plan.title")}${warning ? ` · ${warning}` : ""}`}
      onClick={onToggle}
    >
      <CalendarClock aria-hidden="true" />
      {t("operations.plan.title")}
      {failed && (
        <AlertTriangle className="schedule-plan-warning" aria-hidden="true" />
      )}
    </button>
  );
}

export function SchedulePlan({
  schedules,
  task,
  id,
}: {
  schedules: Schedule[];
  task?: ScheduleTask;
  id?: string;
}) {
  const { t, i18n } = useTranslation();
  const date = (value: string | null, timezone: string) =>
    value
      ? new Intl.DateTimeFormat(
          i18n?.resolvedLanguage === "zh" ? "zh-CN" : "en-US",
          {
            timeZone: timezone,
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          },
        ).format(new Date(value))
      : "—";
  return (
    <section
      className="schedule-plan"
      id={id}
      aria-label={t("operations.plan.title")}
    >
      {schedules.map((schedule) => {
        const fixed = /^(\d{1,2}) (\d{1,2}) \* \* (1-5|\*)$/.exec(
          schedule.cron,
        );
        const time =
          fixed && +fixed[1] < 60 && +fixed[2] < 24
            ? t(
                `operations.plan.${fixed[3] === "1-5" ? "weekdays" : "daily"}`,
                {
                  time: `${fixed[2].padStart(2, "0")}:${fixed[1].padStart(2, "0")}`,
                },
              )
            : t("operations.plan.custom");
        const last = schedule.last_trigger;
        const earlier = isEarlierSubmission(schedule, task);
        const warning = last?.state === "failed" && !earlier;
        const conflict =
          schedule.job === "submit" &&
          last?.state === "failed" &&
          /^FileExistsError:\s*Active Task already exists(?::|$)/.test(
            last.error,
          );
        return (
          <div className="schedule-plan-item" key={schedule.name}>
            {schedules.length > 1 && <strong>{schedule.name}</strong>}
            <dl className="schedule-plan-facts">
              <div>
                <dt>{t("operations.plan.time")}</dt>
                <dd>
                  {time} ·{" "}
                  {schedule.timezone === "Asia/Shanghai"
                    ? t("onlineWorkbench.timezone")
                    : schedule.timezone}
                </dd>
              </div>
              <div>
                <dt>{t("schedules.nextRun")}</dt>
                <dd>{date(schedule.next_run_at, schedule.timezone)}</dd>
              </div>
            </dl>
            <p
              className={`schedule-plan-last${earlier ? " is-history" : ""}`}
              role={warning ? "status" : undefined}
            >
              <span>
                {t(
                  schedule.job === "submit"
                    ? "operations.plan.submissionHistory"
                    : "operations.lastExecution",
                )}
              </span>
              {last ? (
                <>
                  <time dateTime={last.triggered_at}>
                    {date(last.triggered_at, schedule.timezone)}
                  </time>
                  <span className={warning ? "schedule-plan-warning" : ""}>
                    {conflict
                      ? t("operations.plan.conflict")
                      : t(
                          schedule.job === "submit"
                            ? `operations.plan.states.${last.state}`
                            : `states.${last.state}`,
                        )}
                    {earlier && ` ${t("operations.plan.newerTask")}`}
                  </span>
                </>
              ) : (
                <span>{t("operations.noTriggers")}</span>
              )}
            </p>
            <details className="schedule-plan-technical">
              <summary>{t("operations.technicalDetails")}</summary>
              <pre>
                {JSON.stringify(
                  {
                    name: schedule.name,
                    job: schedule.job,
                    cron: schedule.cron,
                    timezone: schedule.timezone,
                    concurrency_policy: schedule.concurrency_policy,
                    running: schedule.running,
                    arguments: schedule.arguments,
                    last_trigger: last,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </div>
        );
      })}
    </section>
  );
}
