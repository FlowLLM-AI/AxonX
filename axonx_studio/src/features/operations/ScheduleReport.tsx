import { useTranslation } from "react-i18next";
import { CalendarClock, Clock3, Globe2, SlidersHorizontal } from "lucide-react";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import type { Schedule } from "../tasks/types";
import type { ScheduleRun } from "../../shared/api/contracts";
import { isRecord } from "../../shared/lib/values";

function Result({ value }: { value: unknown }) {
  const { t } = useTranslation();
  if (value == null) return null;
  const metrics = isRecord(value)
    ? Object.entries(value).filter(
        ([, v]) => typeof v === "number" || Array.isArray(v),
      )
    : [];
  return (
    <>
      {metrics.length > 0 && (
        <dl className="operation-metrics">
          {metrics.map(([key, v]) => (
            <div key={key}>
              <dt>{t(`operations.metrics.${key}`, key)}</dt>
              <dd>{Array.isArray(v) ? v.length : String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      <details className="operation-disclosure">
        <summary>{t("operations.result")}</summary>
        <pre>{JSON.stringify(value, null, 2)}</pre>
      </details>
    </>
  );
}

export function ScheduleReport({
  name,
  schedule,
}: {
  name: string;
  schedule: Schedule | null;
}) {
  const { t } = useTranslation();
  return (
    <article className="schedule-card operation-detail">
      <header className="operation-detail-header">
        <span className="operation-detail-icon">
          <CalendarClock />
        </span>
        <div>
          <p className="eyebrow">{t("operations.configuration")}</p>
          <h2>{name}</h2>
          {schedule && (
            <span className="operation-job-name">{schedule.job}</span>
          )}
        </div>
        {schedule?.last_trigger && (
          <Status state={schedule.last_trigger.state} />
        )}
      </header>
      {!schedule ? (
        <p className="muted">{t("schedules.removed")}</p>
      ) : (
        <>
          {schedule.description && (
            <p className="operation-description">{schedule.description}</p>
          )}
          <div className="operation-config-strip">
            <span>
              <Clock3 />
              <code>{schedule.cron}</code>
            </span>
            <span>
              <Globe2 />
              {schedule.timezone}
            </span>
            <span>
              <SlidersHorizontal />
              {t(`schedules.policies.${schedule.concurrency_policy}`)}
            </span>
          </div>
          <dl className="operation-facts">
            <div>
              <dt>{t("schedules.nextRun")}</dt>
              <dd>{formatDate(schedule.next_run_at)}</dd>
            </div>
            <div>
              <dt>{t("operations.activeJobs")}</dt>
              <dd>{schedule.running}</dd>
            </div>
            <div>
              <dt>{t("schedules.lastJob")}</dt>
              <dd>{formatDate(schedule.last_trigger?.triggered_at ?? null)}</dd>
            </div>
          </dl>
          {schedule.last_trigger?.error && (
            <p className="error-state" role="alert">
              {schedule.last_trigger.error}
            </p>
          )}
          {schedule.last_trigger ? (
            <Result value={schedule.last_trigger.result} />
          ) : (
            <p className="operation-index-empty">
              {t("operations.noTriggers")}
            </p>
          )}
          {Object.keys(schedule.arguments).length > 0 && (
            <details className="operation-disclosure">
              <summary>{t("schedules.arguments")}</summary>
              <pre>{JSON.stringify(schedule.arguments, null, 2)}</pre>
            </details>
          )}
        </>
      )}
    </article>
  );
}

export function ScheduleRunReport({ run }: { run: ScheduleRun }) {
  const { t } = useTranslation();
  return (
    <article className="online-report operation-job-report operation-detail">
      <header>
        <div>
          <p className="eyebrow">{t("operations.jobRun")}</p>
          <h2>{run.name}</h2>
          <details className="pipeline-identity">
            <summary>{run.trigger_id}</summary>
            <small>{run.scheduler_id}</small>
          </details>
        </div>
        <Status state={run.state} />
      </header>
      <dl className="operation-facts">
        <div>
          <dt>{t("operations.triggered")}</dt>
          <dd>{formatDate(run.triggered_at)}</dd>
        </div>
        <div>
          <dt>{t("operations.finished")}</dt>
          <dd>{formatDate(run.finished_at)}</dd>
        </div>
        <div>
          <dt>{t("operations.jobRun")}</dt>
          <dd>{run.job}</dd>
        </div>
      </dl>
      {run.error && (
        <p className="error-state" role="alert">
          {run.error}
        </p>
      )}
      <Result value={run.result} />
    </article>
  );
}
