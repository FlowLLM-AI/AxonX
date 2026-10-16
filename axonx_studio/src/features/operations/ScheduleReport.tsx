import { useTranslation } from "react-i18next";
import { ScheduleCard } from "../tasks/ScheduleCard";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import type { Schedule } from "../tasks/types";
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
  const history =
    schedule?.history ||
    (schedule?.last_trigger ? [schedule.last_trigger] : []);
  return (
    <ScheduleCard name={name} schedule={schedule}>
      <Result value={schedule?.last_trigger?.result} />
      <h3>{t("operations.history")}</h3>
      {!history.length && <p className="muted">{t("operations.noTriggers")}</p>}
      {[...history].reverse().map((run) => (
        <details className="operation-trigger" key={run.trigger_id}>
          <summary>
            <Status state={run.state} />
            <time>{formatDate(run.triggered_at)}</time>
          </summary>
          <small>{run.trigger_id}</small>
          <p>
            {t("operations.finished")} · {formatDate(run.finished_at)}
          </p>
          {run.error && (
            <p className="error-state" role="alert">
              {run.error}
            </p>
          )}
          <Result value={run.result} />
        </details>
      ))}
    </ScheduleCard>
  );
}
