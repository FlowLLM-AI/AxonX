import { lazy, Suspense, useId, useState } from "react";
import { ArrowUpRight, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { parseHash, routeHash } from "../../app/routes";
import { ReportTabs } from "../../shared/ui/ReportTabs";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import type { TaskMetadata, TaskStepStatus } from "../tasks/types";
import type { TaskNode } from "../tasks/tree";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { ComparisonResults } from "./ComparisonResults";
import { ModelPicker } from "./ModelPicker";
import type { BacktestArtifact } from "../research/backtest/types";
const BacktestView = lazy(() =>
  import("../research/backtest/BacktestView").then((module) => ({
    default: module.BacktestView,
  })),
);
import {
  compareModels,
  compareStageState,
  ownedCompareNodes,
  compareError,
} from "./compare";

export function ComparePipeline({
  parent,
  nodes,
  target,
  onOpenTask,
  refreshedAt,
  error,
}: {
  parent: TaskMetadata;
  nodes: TaskNode[];
  target?: string;
  onOpenTask: (id: string) => void;
  refreshedAt: string;
  error?: string;
}) {
  const { t, i18n } = useTranslation();
  const models = compareModels(parent, nodes);
  const preferred =
    models.find(
      (m) =>
        ["failed", "cancelled"].includes(m.state) ||
        (m.finding &&
          !["consistent", "skipped"].includes(String(m.finding.status))),
    ) || models[0];
  const [selectedModel, setModel] = useState(preferred?.name || "");
  const model = models.find((m) => m.name === selectedModel) || preferred;
  const [currentStage, chooseStage] = useState("logs");
  const [logIds, setLogIds] = useState<Record<string, string>>({});
  const panelId = `${useId()}-compare-content`;
  const rootRecords = [
    ...new Map(parent.children.map((r) => [r.node_name, r])).values(),
  ];
  const publicNodes = ownedCompareNodes(
    rootRecords.filter((r) => !models.some((m) => m.roots.includes(r))),
    nodes,
  );
  const preparation = ["logs", "download"].includes(currentStage);
  const currentNodes = preparation ? publicNodes : model?.children || [];
  const steps = preparation
    ? parent.steps.filter((step) => step.group === "download")
    : model?.steps || [];
  const identity = (node: TaskNode) =>
    `${node.record.task_id}:${node.record.run_id}`;
  const stageNodes =
    currentStage === "logs"
      ? []
      : currentNodes.filter((node) => {
          const kind =
            node.status?.task_type || node.record.task_id?.split("#")[0];
          if (currentStage === "download") return true;
          if (currentStage === "etl")
            return kind === "etl" || /history/.test(node.record.task);
          if (currentStage === "prediction") return kind === "predict";
          if (currentStage === "results")
            return /compare/.test(node.record.task);
          return kind === "backtest";
        });
  const scope = preparation ? currentStage : `${model?.name}:${currentStage}`;
  const source = logIds[scope]
    ? stageNodes.find((node) => identity(node) === logIds[scope])
    : stageNodes[0];
  const logs = currentStage === "logs" ? parent : source?.status;
  const badge = (state: string) => (
    <span className={`online-status status-${state}`}>
      {["done", "succeeded"].includes(state)
        ? t("onlineWorkbench.states.done")
        : t(`onlinePipeline.status.${state}`, state)}
    </span>
  );
  const stageNode = (step: TaskStepStatus) => {
    const phase = step.name.split(":").at(-1);
    return currentNodes.find((node) => {
      const task = node.status?.task_type || node.record.task_id?.split("#")[0];
      return phase === "etl"
        ? /history/.test(node.record.task) || task === "etl"
        : phase === "prediction"
          ? task === "predict"
          : phase === "comparison"
            ? /compare/.test(node.record.task)
            : phase === "backtest"
              ? task === "backtest"
              : preparation;
    });
  };
  const stageRows = (selected: TaskStepStatus[]) =>
    selected.length ? (
      <div className="compare-stage-list">
        {selected.map((step) => {
          const state = compareStageState(step, parent);
          const node = stageNode(step);
          const failedChild = node?.status?.error || node?.record.error;
          const rawError =
            state === "failed"
              ? failedChild || step.error || String(model?.outcome.error || "")
              : step.error;
          const reason =
            rawError && rawError !== "upstream_failed"
              ? compareError(rawError)
              : "";
          const notes =
            node?.status?.steps
              .filter((s) => s.parent && s.phase)
              .map((s) => s.phase) || [];
          return (
            <section
              className={`compare-stage-row state-${state}`}
              key={step.name}
            >
              <div className="compare-stage-main">
                <strong>
                  {t(
                    `onlinePipeline.phases.${step.label || step.name}`,
                    step.label || step.name,
                  )}
                </strong>
                {badge(state)}
                {!reason && notes.length > 0 && (
                  <span className="compare-stage-note">
                    {[...new Set(notes)]
                      .map((note) =>
                        t(`onlinePipeline.phases.${note}`, note || ""),
                      )
                      .join(" · ")}
                  </span>
                )}
                <div className="compare-stage-actions">
                  {node?.record.task_id && (
                    <button
                      className="compare-text-action"
                      onClick={() => onOpenTask(node.record.task_id!)}
                    >
                      {t("onlinePipeline.openTask")}
                      <ArrowUpRight aria-hidden="true" />
                    </button>
                  )}
                </div>
              </div>
              {reason && (
                <p className="compare-stage-reason">
                  {t(`onlinePipeline.reasons.${reason}`, reason)}
                </p>
              )}
              {Object.keys(step.files || {}).length > 0 && (
                <div className="compare-artifacts">
                  {Object.entries(step.files || {}).map(([role, path]) => (
                    <a
                      key={role}
                      href={routeHash(
                        parseHash(window.location.hash).machineId,
                        { section: "workspace", view: "files", resource: path },
                      )}
                    >
                      <FileText aria-hidden="true" />
                      {path.split("/").at(-1)}
                    </a>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    ) : null;
  const ledger =
    model?.children.filter(
      (node) =>
        node.record.task_id?.startsWith("backtest#") &&
        !!node.status?.output_params.universes,
    ) || [];
  const stageTabs = [
    { id: "logs", label: t("nightly.workflowLog") },
    { id: "download", label: t("nightly.dataCompletion") },
    { id: "etl", label: t("nightly.featureUpdate") },
    { id: "prediction", label: t("nightly.offlinePrediction") },
    { id: "results", label: t("nightly.signalComparison") },
    { id: "portfolio", label: t("nightly.backtestAnalysis") },
  ];
  const phase = {
    etl: "etl",
    prediction: "prediction",
    results: "comparison",
    portfolio: "backtest",
  }[currentStage];
  const selectedSteps = preparation
    ? currentStage === "download"
      ? steps
      : []
    : steps.filter(
        (step) =>
          step.name.endsWith(`:${phase}`) ||
          (currentStage === "results" && step.name.endsWith(":online_source")),
      );
  const logToolbar = (
    <div className="daily-log-source">
      {stageNodes.length > 1 ? (
        <label className="pipeline-log-source">
          {t("onlinePipeline.logSource")}
          <select
            value={source ? identity(source) : ""}
            onChange={(event) =>
              setLogIds((value) => ({
                ...value,
                [scope]: event.target.value,
              }))
            }
          >
            {logIds[scope] && !source && (
              <option value={logIds[scope]}>
                {t("onlinePipeline.replacedRun")}
              </option>
            )}
            {stageNodes.map((node) => (
              <option key={identity(node)} value={identity(node)}>
                {node.record.node_name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <span className="daily-log-caption">
          {stageTabs.find((tab) => tab.id === currentStage)?.label}
        </span>
      )}
      {logs && (
        <button
          className="compare-text-action"
          onClick={() => onOpenTask(logs.task_id)}
        >
          {t("onlinePipeline.openTask")}
          <ArrowUpRight aria-hidden="true" />
        </button>
      )}
    </div>
  );
  const logPanel = logs ? (
    <TaskLogPanel
      key={`${target}:${logs.task_id}:${logs.run_id}`}
      task={logs}
      target={target}
      toolbar={logToolbar}
    />
  ) : (
    <>
      {(stageNodes.length > 0 || logIds[scope]) && (
        <div className="pipeline-log-controls">{logToolbar}</div>
      )}
      {source || logIds[scope] ? (
        <p className="online-warning" role="alert">
          {source?.error || t("onlinePipeline.replacedRun")}
        </p>
      ) : (
        <p className="empty-state">{t("nightly.noStageRun")}</p>
      )}
    </>
  );
  const knownErrors = [
    ...parent.steps.map((step) => step.error),
    ...models.flatMap((m) => [
      m.outcome.error,
      ...m.children.flatMap((node) => [node.record.error, node.status?.error]),
    ]),
  ].filter(
    (message): message is string => typeof message === "string" && !!message,
  );
  const parentError =
    parent.error &&
    !/^Task exited with code \d+\s*$/.test(parent.error) &&
    !knownErrors.some((message) =>
      compareError(parent.error!).includes(compareError(message)),
    )
      ? parent.error
      : "";
  return (
    <article className="online-report pipeline-report online-daily-workbench compare-workbench">
      <ReplicaNotice replica={parent.replica} state={parent.state} />
      <header className="compare-header">
        <div className="compare-heading">
          <p className="eyebrow">{t("onlinePipeline.nightly")}</p>
          <h2>{String(parent.input_params.task_name || parent.reg_name)}</h2>
        </div>
        <div className="compare-header-actions">
          <small className="compare-refresh-hint">
            {t("onlineWorkbench.updated")}{" "}
            {new Date(refreshedAt).toLocaleString(
              i18n?.resolvedLanguage === "zh" ? "zh-CN" : "en-US",
              { timeZone: "Asia/Shanghai", hour12: false },
            )}{" "}
            · {t("onlinePipeline.refreshHint")}
          </small>
          <button
            className="secondary-button"
            onClick={() => onOpenTask(parent.task_id)}
          >
            {t("onlinePipeline.openTask")}
          </button>
        </div>
      </header>
      {error && (
        <p className="online-warning" role="alert">
          {error}
        </p>
      )}
      {parentError && (
        <p className="online-warning" role="alert">
          {compareError(parentError)}
        </p>
      )}
      {parent.output_params.status === "market_closed" ? (
        <p className="compare-empty">{t("onlinePipeline.closed")}</p>
      ) : (
        <>
          <ReportTabs
            selected={currentStage}
            onSelected={chooseStage}
            panelId={panelId}
            ariaLabel={t("onlineWorkbench.stageLabel")}
            tabs={stageTabs}
            actions={
              <ModelPicker
                models={models.map((m) => m.name)}
                value={model?.name || ""}
                onChange={setModel}
              />
            }
          />
          <section
            id={panelId}
            className="compare-panel"
            role="tabpanel"
            aria-label={stageTabs.find((tab) => tab.id === currentStage)?.label}
          >
            {!preparation && model && (
              <div className="compare-active-model">
                <strong>{model.name}</strong>
                <small>{model.provider}</small>
                {badge(model.state)}
              </div>
            )}
            {!preparation && stageRows(selectedSteps)}
            {stageNodes
              .filter((node) => node.error && node.status)
              .map((node) => (
                <p className="online-warning" role="alert" key={identity(node)}>
                  {node.error}
                </p>
              ))}
            {currentStage === "results" &&
              typeof model?.outcome.error === "string" &&
              !steps.some((step) => step.state === "failed") && (
                <p className="online-warning">
                  {compareError(model.outcome.error)}
                </p>
              )}
            {currentStage === "results" && model && (
              <ComparisonResults model={model} />
            )}
            {currentStage === "portfolio" && model && (
              <>
                {ledger.map((node) => (
                  <Suspense
                    key={identity(node)}
                    fallback={<p>{t("shell.loading")}</p>}
                  >
                    <BacktestView
                      meta={node.status as unknown as BacktestArtifact}
                      target={target}
                    />
                  </Suspense>
                ))}
                <ComparisonResults model={model} portfolio />
              </>
            )}
            {logPanel}
          </section>
        </>
      )}
    </article>
  );
}
