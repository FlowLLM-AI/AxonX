import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { getTaskStatus } from "../tasks/api";
import { TaskChildren } from "../tasks/TaskChildren";
import { readTaskChildren } from "../tasks/tree";
import { ComparePipeline } from "./ComparePipeline";
import type { TaskRunIdentity } from "../tasks/types";
import { TaskSteps } from "../tasks/TaskSteps";
import { Status } from "../tasks/TaskRow";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { usePolling } from "../../shared/hooks/usePolling";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { TaskQuality } from "./QualityReport";
import { StockReport } from "./StockReport";
import { parseOnlineReport } from "./types";
import { Outcome } from "./Outcome";

export function PipelineReport({
  task,
  target,
  onOpenTask,
}: {
  task: TaskRunIdentity;
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
      const nodes = await readTaskChildren(parent, target, signal, {
        replaced: t("onlinePipeline.replacedRun"),
        snapshot: t("onlinePipeline.changedSnapshot"),
      });
      const children = nodes.map((node) => {
        try {
          return {
            ...node,
            report:
              node.status?.report_kind === "online"
                ? parseOnlineReport(node.status.output_params).report
                : null,
          };
        } catch (reason) {
          return { ...node, report: null, error: String(reason) };
        }
      });
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
  const compare = parent.report_kind === "compare_pipeline";
  const collection = parent.steps.filter((step) => step.group === "collection");
  const current = parent.steps.filter(
    (step) => step.parent && step.state === "running",
  );
  const planned = Object.entries(
    (pipeline ? parent.input_params.models || {} : {}) as Record<
      string,
      { task_name: string }[]
    >,
  );
  const models = planned.flatMap(([slot, entries]) =>
    entries.map((model) => {
      const id = `${model.task_name}:${slot}`;
      return {
        slot,
        name: model.task_name,
        id,
        record: [...parent.children]
          .reverse()
          .find(
            (child) =>
              child.node_name === `${model.task_name}-${slot}-${child.task}` &&
              child.task_id?.startsWith("inference#"),
          ),
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
            {compare
              ? t("onlinePipeline.nightly")
              : t(`onlinePipeline.kinds.${parent.task_type}`, parent.task_type)}
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
        <Status state={parent.state} />
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
      {!compare && (
        <>
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
                {upcoming
                  ? `${upcoming.slice(0, 2)}:${upcoming.slice(2)}`
                  : "—"}
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
        </>
      )}
      {compare && (
        <ComparePipeline
          parent={parent}
          nodes={children}
          target={target}
          onOpenTask={onOpenTask}
        />
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
          <h3>{t("onlinePipeline.history")}</h3>
          <TaskSteps
            steps={parent.steps.filter((step) => step.group === "history")}
          />
          <TaskChildren
            records={parent.children.filter((child) =>
              child.task_id?.startsWith("composite#"),
            )}
            nodes={children}
            onOpenTask={onOpenTask}
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
                  <span className={`online-status status-${modelState}`}>
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
        !pipeline && !compare && runtime
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
              {child.reg_name} · {child.input_params.task_name as string}
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
