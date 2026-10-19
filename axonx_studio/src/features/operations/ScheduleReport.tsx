import { ReportTabs } from "../../shared/ui/ReportTabs";
import { useTranslation } from "react-i18next";
import {
  CalendarClock,
  Clock3,
  Globe2,
  SlidersHorizontal,
  RefreshCw,
} from "lucide-react";
import { Status } from "../tasks/TaskRow";
import { formatDate } from "../tasks/format";
import type { Schedule } from "../tasks/types";
import type { ScheduleRun } from "../../shared/api/contracts";
import { OperationResult } from "./OperationResult";

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
          <span className="operation-last-state">
            {t("operations.lastExecution")}{" "}
            <Status state={schedule.last_trigger.state} />
          </span>
        )}
      </header>
      {!schedule ? (
        <p className="muted">{t("schedules.removed")}</p>
      ) : (
        <ReportTabs
          tabs={[
            {
              id: "configuration",
              label: t("operations.configuration"),
              content: (
                <>
                  {schedule.description && (
                    <p className="operation-description">
                      {schedule.description}
                    </p>
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
                      <dd>
                        {formatDate(
                          schedule.last_trigger?.triggered_at ?? null,
                        )}
                      </dd>
                    </div>
                  </dl>
                  {schedule.last_trigger?.error && (
                    <p className="error-state" role="alert">
                      {schedule.last_trigger.error}
                    </p>
                  )}
                  {Object.keys(schedule.arguments).length > 0 && (
                    <details className="operation-result-details">
                      <summary>{t("schedules.arguments")}</summary>
                      <pre>{JSON.stringify(schedule.arguments, null, 2)}</pre>
                    </details>
                  )}
                </>
              ),
            },
            {
              id: "result",
              label: t("operations.result"),
              content: (
                <>
                  {" "}
                  {schedule.last_trigger ? (
                    <OperationResult value={schedule.last_trigger.result} />
                  ) : (
                    <p className="operation-index-empty">
                      {t("operations.noTriggers")}
                    </p>
                  )}
                </>
              ),
            },
          ]}
        />
      )}
    </article>
  );
}

export function ScheduleRunReport({ run }: { run: ScheduleRun }) {
  const { t } = useTranslation();
  return (
    <article className="online-report operation-job-report operation-detail">
      <header>
        <span className="operation-detail-icon">
          <RefreshCw aria-hidden="true" />
        </span>
        <div>
          <p className="eyebrow">{t("operations.jobRun")}</p>
          <h2>{run.name}</h2>
          <p className="operation-run-time">{formatDate(run.triggered_at)}</p>
        </div>
        <Status state={run.state} />
      </header>
      {run.error && (
        <p className="error-state" role="alert">
          {run.error}
        </p>
      )}
      <ReportTabs
        defaultTab="result"
        tabs={[
          {
            id: "execution",
            label: t("operations.jobRun"),
            content: (
              <>
                {" "}
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
                <details className="operation-result-details">
                  <summary>{t("operations.technicalDetails")}</summary>
                  <dl className="operation-facts">
                    <div>
                      <dt>Trigger ID</dt>
                      <dd>{run.trigger_id}</dd>
                    </div>
                    <div>
                      <dt>Scheduler ID</dt>
                      <dd>{run.scheduler_id}</dd>
                    </div>
                  </dl>
                </details>
              </>
            ),
          },
          {
            id: "result",
            label: t("operations.result"),
            content: <OperationResult value={run.result} />,
          },
        ]}
      />
    </article>
  );
}
