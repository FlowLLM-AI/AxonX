import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { getTaskStatus } from "../tasks/api";
import type { TaskSummary } from "../tasks/types";
import { TaskSteps } from "../tasks/TaskSteps";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { usePolling } from "../../shared/hooks/usePolling";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { QualityReport, TaskQuality } from "./QualityReport";
import { StockReport } from "./StockReport";
import { parseOnlineReport, type OnlineOutcome } from "./types";
import { parseQuality } from "./quality";

export function PipelineReport({
  task,
  target,
  onOpenTask,
}: {
  task: TaskSummary;
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [logId, setLogId] = useState("");
  const load = useCallback(
    async (signal: AbortSignal) => {
      const parent = await getTaskStatus(task.task_id, target, signal);
      if (parent.run_id !== task.run_id)
        throw new Error(t("onlinePipeline.replacedRun"));
      const children = await Promise.all(
        Array.from(
          new Map(
            parent.children
              .filter((child) => child.task_id)
              .map((child) => [child.task_id, child]),
          ).values(),
        ).map(async (child) => {
          try {
            const status = await getTaskStatus(child.task_id!, target, signal);
            if (status.run_id !== child.run_id)
              return {
                status: null,
                report: null,
                error: t("onlinePipeline.replacedRun"),
              };
            if (
              parent.replica?.snapshot &&
              status.replica?.snapshot?.revision !==
                parent.replica.snapshot.revision
            )
              return {
                status: null,
                report: null,
                error: t("onlinePipeline.changedSnapshot"),
              };
            try {
              return {
                status,
                report: parseOnlineReport(status.output_params).report,
                error: "",
              };
            } catch (reason) {
              return { status, report: null, error: String(reason) };
            }
          } catch (reason) {
            signal.throwIfAborted();
            return { status: null, report: null, error: String(reason) };
          }
        }),
      );
      return {
        parent,
        children,
        output: parseOnlineReport(parent.output_params),
      };
    },
    [task.task_id, task.run_id, target, t],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  const refresh = useCallback(async () => {
    await reload();
  }, [reload]);
  usePolling(refresh, true);
  if (!data)
    return (
      <article className="online-report">
        <p role={error ? "alert" : "status"}>
          {error || (loading ? t("shell.loading") : t("onlinePipeline.empty"))}
        </p>
        <button onClick={() => void reload()}>{t("retry")}</button>
      </article>
    );
  const { parent, children, output } = data;
  const pipeline = parent.report_kind === "online_pipeline";
  const collection = parent.steps.filter((step) => step.group === "collection");
  const current = parent.steps.filter(
    (step) => step.parent && step.state === "running",
  );
  const planned = Object.entries(
    (parent.input_params.models || {}) as Record<
      string,
      { task_name: string }[]
    >,
  );
  const models = planned.flatMap(([slot, entries]) =>
    entries.map((model) => {
      const id = `${model.task_name}-${slot}-a_stock_online_predict`;
      return {
        slot,
        name: model.task_name,
        id,
        record: [...parent.children]
          .reverse()
          .find((child) => child.node_name === id),
      };
    }),
  );
  const upcoming = !["queued", "running"].includes(parent.state)
    ? undefined
    : planned
        .map(([slot]) => slot)
        .sort()
        .find((slot) =>
          models.some((model) => model.slot === slot && !model.record),
        );
  const statuses = children.flatMap((item) =>
    item.status ? [item.status] : [],
  );
  const logs = logId
    ? statuses.find((child) => child.task_id === logId)
    : parent;
  const rows = output.windows || output.comparisons || [];
  const runtime = (
    <>
      <h3>
        {t(
          parent.task_type === "analysis"
            ? "onlinePipeline.comparisons"
            : "onlinePipeline.windows",
        )}
      </h3>
      {output.model_identity && (
        <div className="online-model">
          {Object.entries(output.model_identity).map(([key, value]) => (
            <span key={key}>
              <small>{key}</small>
              <code>{value}</code>
            </span>
          ))}
        </div>
      )}
      <TaskSteps steps={parent.steps.filter((step) => step.parent)} />
      {rows.map((row) => (
        <Outcome
          key={row.key}
          row={row}
          taskId={parent.task_id}
          target={target}
        />
      ))}
    </>
  );
  return (
    <article className="online-report">
      <ReplicaNotice replica={parent.replica} state={parent.state} />
      <header>
        <div>
          <p className="eyebrow">
            {t(`onlinePipeline.kinds.${parent.task_type}`, parent.task_type)}
          </p>
          <h2>
            {String(
              parent.input_params.trade_date ??
                task.display_name ??
                task.reg_name,
            )}
          </h2>
          <details className="pipeline-identity">
            <summary>{parent.task_id}</summary>
            <small>{parent.run_id}</small>
          </details>
        </div>
        <button
          className="secondary-button"
          onClick={() => onOpenTask(parent.task_id)}
        >
          {t("onlinePipeline.openTask")}
        </button>
      </header>
      {(error || parent.error) && (
        <div className="error-state" role="alert">
          {error || parent.error}
          <button onClick={() => void reload()}>{t("retry")}</button>
        </div>
      )}
      <div className="online-summary">
        <div>
          <span>{t("onlinePipeline.runState")}</span>
          <strong>
            {t(`onlinePipeline.status.${parent.state}`, parent.state)}
          </strong>
        </div>
        <div>
          <span>{t("onlinePipeline.collection")}</span>
          <strong>
            {collection.filter((item) => item.state === "done").length} /{" "}
            {collection.length}
          </strong>
        </div>
        <div>
          <span>{t("onlinePipeline.models")}</span>
          <strong>
            {
              models.filter((model) => model.record?.state === "succeeded")
                .length
            }{" "}
            / {models.length}
          </strong>
        </div>
      </div>
      <div className="pipeline-now">
        <div>
          <span>{t("onlinePipeline.currentAction")}</span>
          <strong>
            {current.length
              ? current
                  .map((item) =>
                    t(
                      `onlinePipeline.phases.${item.phase || item.label || item.name}`,
                      item.phase || item.label || item.name,
                    ),
                  )
                  .join(" · ")
              : t(`onlinePipeline.status.${parent.state}`, parent.state)}
          </strong>
        </div>
        <div>
          <span>{t("onlinePipeline.nextSignal")}</span>
          <strong>
            {upcoming ? `${upcoming.slice(0, 2)}:${upcoming.slice(2)}` : "—"}
          </strong>
        </div>
        <small>{t("onlinePipeline.refreshHint")}</small>
      </div>
      {!collection.length && !models.length && (
        <p>
          {t(
            parent.output_params.status === "market_closed"
              ? "onlinePipeline.closed"
              : "onlinePipeline.pending",
          )}
        </p>
      )}
      {pipeline && (
        <>
          <h3>{t("onlinePipeline.collection")}</h3>
          <p className="muted">{t("onlinePipeline.collectionHint")}</p>
          <TaskSteps steps={collection} />
          <TaskQuality
            windows={parent.output_params.windows}
            taskId={parent.task_id}
            target={target}
          />
          <h3>{t("onlinePipeline.models")}</h3>
          {models.map((model) => {
            const record = model.record;
            const entry = children.find(
              (item) => item.status?.run_id === record?.run_id,
            );
            const child = entry?.status;
            const outcomes = parent.output_params.models as
              Record<string, Record<string, unknown>> | undefined;
            const slotOutcome = outcomes?.[model.slot];
            const outcome = (slotOutcome?.[model.name] || slotOutcome) as
              { status?: string; error?: string; reason?: string } | undefined;
            const modelState =
              record?.state ||
              outcome?.status ||
              (["queued", "running"].includes(parent.state)
                ? "pending"
                : "skipped");
            const modelError =
              record?.error || outcome?.error || outcome?.reason;
            const active = child?.steps.find(
              (step) => step.parent && step.state === "running",
            );
            return (
              <section key={model.id} className="pipeline-model">
                <header>
                  <strong>
                    {model.slot} · {model.name}
                  </strong>
                  <span>
                    {t(`onlinePipeline.status.${modelState}`, modelState)}
                  </span>
                  {active && (
                    <span>
                      {t(`onlinePipeline.phases.${active.name}`, active.name)}
                    </span>
                  )}
                </header>
                {modelError && (
                  <p className="error-state">
                    {t(`onlinePipeline.reasons.${modelError}`, modelError)}
                  </p>
                )}
                {child && (
                  <details open={record?.state === "running"}>
                    <summary>{t("onlinePipeline.stageDetails")}</summary>
                    <button
                      className="secondary-button"
                      onClick={() => onOpenTask(child.task_id)}
                    >
                      {t("onlinePipeline.openTask")}
                    </button>
                    <TaskSteps
                      compact
                      steps={child.steps.filter((step) => step.parent)}
                    />
                    {entry?.report && (
                      <StockReport
                        report={entry.report}
                        target={target}
                        runtime={null}
                      />
                    )}
                  </details>
                )}
              </section>
            );
          })}
        </>
      )}
      {output.report ? (
        <StockReport report={output.report} target={target} runtime={runtime} />
      ) : (
        !pipeline && runtime
      )}
      {children
        .filter((child) => child.error)
        .map((child, index) => (
          <p className="error-state" key={index}>
            {child.error}
          </p>
        ))}
      <h3>{t("taskDetail.logs")}</h3>
      <label className="pipeline-log-source">
        {t("onlinePipeline.logSource")}
        <select
          value={logId}
          onChange={(event) => setLogId(event.target.value)}
        >
          <option value="">{t("onlinePipeline.chainLog")}</option>
          {statuses.map((child) => (
            <option key={child.run_id} value={child.task_id}>
              {child.input_params.task_name as string}
            </option>
          ))}
        </select>
      </label>
      {logs ? (
        <TaskLogPanel
          key={`${target}:${logs.task_id}:${logs.run_id}`}
          task={logs}
          target={target}
        />
      ) : (
        <p>{t("onlinePipeline.replacedRun")}</p>
      )}
    </article>
  );
}

function Outcome({
  row,
  taskId,
  target,
}: {
  row: OnlineOutcome;
  taskId: string;
  target?: string;
}) {
  const { t } = useTranslation();
  const coverage = "coverage" in row ? row.coverage : null;
  const rows = "rows" in row ? row.rows : null;
  const elapsed = "elapsed_seconds" in row ? row.elapsed_seconds : null;
  return (
    <section className="online-outcome">
      <header>
        <strong>{row.key}</strong>
        <span className={`online-status status-${row.status}`}>
          {t(`onlinePipeline.status.${row.status}`, row.status)}
        </span>
      </header>
      <div className="online-metrics">
        {coverage != null && (
          <div>
            <span>{t("onlinePipeline.coverage")}</span>
            <strong>{(coverage * 100).toFixed(1)}%</strong>
            <progress max={1} value={coverage} />
          </div>
        )}
        {rows != null && (
          <div>
            <span>{t("onlinePipeline.rows")}</span>
            <strong>{rows.toLocaleString()}</strong>
          </div>
        )}
        {elapsed != null && (
          <div>
            <span>{t("onlinePipeline.elapsed")}</span>
            <strong>{elapsed.toFixed(1)}s</strong>
          </div>
        )}
        {Object.entries(row.metrics || {})
          .filter(([key]) => key !== "quality")
          .map(([key, value]) => (
            <div key={key}>
              <span>{t(`onlinePipeline.metrics.${key}`, key)}</span>
              <strong>
                {typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value)}
              </strong>
            </div>
          ))}
      </div>
      {row.metrics?.quality != null && (
        <QualityReport
          summary={parseQuality(row.metrics.quality)}
          taskId={taskId}
          target={target}
          artifacts={row.artifacts}
        />
      )}
      {row.reason && (
        <p className="online-reason">
          {t(`onlinePipeline.reasons.${row.reason}`, row.reason)}
        </p>
      )}
    </section>
  );
}
