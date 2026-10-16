import { useTranslation } from "react-i18next";
import { ScheduleCard } from "../tasks/ScheduleCard";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import type { Schedule } from "../tasks/types";
import type { ScheduleRun } from "../../shared/api/contracts";
import { isRecord } from "../../shared/lib/values";

function Result({ value }: { value: unknown }) {
  const { t } = useTranslation();
  if (value == null) return null;
  return (
    <>
      {isRecord(value) && (
        <dl className="operation-metrics">
          {Object.entries(value)
            .filter(([, v]) => typeof v === "number" || Array.isArray(v))
            .map(([key, v]) => (
              <div key={key}>
                <dt>{t(`operations.metrics.${key}`, key)}</dt>
                <dd>{Array.isArray(v) ? v.length : String(v)}</dd>
              </div>
            ))}
        </dl>
      )}
      <details>
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
    <ScheduleCard name={name} schedule={schedule}>
      {schedule?.last_trigger ? (
        <Result value={schedule.last_trigger.result} />
      ) : (
        schedule && <p className="muted">{t("operations.noTriggers")}</p>
      )}
    </ScheduleCard>
  );
}

export function ScheduleRunReport({ run }: { run: ScheduleRun }) {
  const { t } = useTranslation();
  return (
    <article className="online-report operation-job-report">
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
      <p>
        {t("operations.triggered")} · {formatDate(run.triggered_at)}
      </p>
      <p>
        {t("operations.finished")} · {formatDate(run.finished_at)}
      </p>
      {run.error && (
        <p className="error-state" role="alert">
          {run.error}
        </p>
      )}
      <Result value={run.result} />
    </article>
  );
}
