import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { Schedule } from "./types";
import { formatDate } from "./format";

export function ScheduleCard({
  name,
  schedule,
  children,
}: {
  name: string;
  schedule: Schedule | null;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <details className="schedule-card" open>
      <summary>
        <strong>{name}</strong>
        {schedule ? (
          <span>
            {schedule.job} · {schedule.cron} · {schedule.timezone}
          </span>
        ) : (
          <span>{t("schedules.removed")}</span>
        )}
      </summary>
      {schedule?.description && (
        <p className="schedule-description">{schedule.description}</p>
      )}
      {schedule && (
        <div className="schedule-status">
          <span>
            {t("schedules.nextRun")} · {formatDate(schedule.next_run_at)}
          </span>
          <span>
            {t("schedules.policy")} ·{" "}
            {t(`schedules.policies.${schedule.concurrency_policy}`)}
          </span>
          <span>{t("schedules.runningJobs", { count: schedule.running })}</span>
          {schedule.last_trigger && (
            <span>
              {t("schedules.lastJob")} ·{" "}
              {formatDate(schedule.last_trigger.triggered_at)} ·{" "}
              {t(`states.${schedule.last_trigger.state}`)}
            </span>
          )}
          {schedule.last_trigger?.error && (
            <p className="schedule-error" role="alert">
              {schedule.last_trigger.error}
            </p>
          )}
        </div>
      )}
      {schedule && Object.keys(schedule.arguments).length > 0 && (
        <details className="schedule-arguments">
          <summary>{t("schedules.arguments")}</summary>
          <pre>{JSON.stringify(schedule.arguments, null, 2)}</pre>
        </details>
      )}
      {children}
    </details>
  );
}
