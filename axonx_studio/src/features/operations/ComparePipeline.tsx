import { ArrowUpRight, FileText } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { parseHash, routeHash } from "../../app/routes";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import type { TaskMetadata } from "../../shared/api/contracts";
import type { TaskStepStatus } from "../../shared/api/event";
import { ReportTabs } from "../../shared/ui/ReportTabs";
import { Picker, Select } from "../../shared/ui/Select";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import type { TaskNode } from "../tasks/tree";
import { ComparisonResults } from "./ComparisonResults";
import {
  compareError,
  compareModels,
  compareStageState,
  ownedCompareNodes,
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
        ["failed"].includes(m.state) ||
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
    `${node.record.child_task_id}:${node.record.started_at}`;
  const stageNodes =
    currentStage === "logs"
      ? []
      : currentStage === "download"
        ? currentNodes
        : ownedCompareNodes(
            model?.roles[
              currentStage === "results" ? "comparison" : currentStage
            ] || [],
            currentNodes,
          );
  const featureLog =
    stageNodes.find(
      (node) =>
        node.status?.state === "failed" || node.record.state === "failed",
    ) ||
    stageNodes
      .filter((node) => node.record.child_task_id?.startsWith("etl#"))
      .at(-1) ||
    stageNodes[0];
  const scope = preparation ? currentStage : `${model?.name}:${currentStage}`;
  const source =
    currentStage === "etl"
      ? featureLog
      : logIds[scope]
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
  const stageRows = (selected: TaskStepStatus[]) =>
    selected.length ? (
      <div className="compare-stage-list">
        {selected.map((step) => {
          const state = compareStageState(step, parent);
          const node = step.name.endsWith(":online_source")
            ? undefined
            : source;
          const failedChild = node?.status?.error || node?.record.error;
          const rawError =
            state === "failed"
              ? failedChild || step.error || String(model?.outcome.error || "")
              : step.error;
          const reason =
            rawError && rawError !== "upstream_failed"
              ? compareError(rawError)
              : "";
          const notes = [
            ...new Set(
              [
                step.phase,
                ...(node?.status?.steps
                  .filter((s) => s.parent && s.phase)
                  .map((s) => s.phase) || []),
              ].filter(Boolean),
            ),
          ];
          return (
            <section
              className={`compare-stage-row state-${state}${!preparation ? " compare-stage-compact" : ""}`}
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
                  {node?.record.child_task_id && (
                    <button
                      className="compare-text-action"
                      onClick={() => onOpenTask(node.record.child_task_id!)}
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
  const stageTabs = [
    { id: "logs", label: t("nightly.workflowLog") },
    { id: "download", label: t("nightly.dataCompletion") },
    { id: "etl", label: t("nightly.featureUpdate") },
    { id: "prediction", label: t("nightly.offlinePrediction") },
    { id: "portfolio", label: t("nightly.portfolioConstruction") },
    { id: "results", label: t("nightly.signalComparison") },
  ];
  const phase = {
    etl: "etl",
    prediction: "prediction",
    portfolio: "portfolio",
    results: "comparison",
  }[currentStage];
  const selectedSteps = preparation
    ? currentStage === "download"
      ? steps
      : []
    : steps.filter(
        (step) =>
          step.name.endsWith(`:${phase}`) ||
          (currentStage === "results" &&
            step.name.endsWith(":online_source") &&
            step.state === "failed"),
      );
  const logToolbar = (
    <div className="daily-log-source">
      {!preparation ? null : stageNodes.length > 1 ? (
        <label className="pipeline-log-source">
          {t("onlinePipeline.logSource")}
          <Select
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
                {t("onlinePipeline.restartedTask")}
              </option>
            )}
            {stageNodes.map((node) => (
              <option key={identity(node)} value={identity(node)}>
                {node.record.node_name}
              </option>
            ))}
          </Select>
        </label>
      ) : (
        <span className="daily-log-caption">
          {stageTabs.find((tab) => tab.id === currentStage)?.label}
        </span>
      )}
      {logs && preparation && (
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
      key={`${target}:${logs.task_id}:${logs.started_at}`}
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
          {source?.error || t("onlinePipeline.restartedTask")}
        </p>
      ) : selectedSteps.some((step) => step.state === "skipped") ? null : (
        <p className="empty-state">{t("nightly.noStageTask")}</p>
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
              <Picker
                value={model?.name || ""}
                onChange={setModel}
                label={t("onlineWorkbench.model")}
                className="online-model-picker"
                options={models.map((m) => ({ value: m.name, label: m.label }))}
              />
            }
          />
          <section
            id={panelId}
            className="compare-panel"
            role="tabpanel"
            aria-label={stageTabs.find((tab) => tab.id === currentStage)?.label}
          >
            {!preparation && !selectedSteps.length && model && (
              <div className="compare-active-model">
                <strong>{model.label}</strong>
                <small>{model.provider}</small>
                {badge(model.state)}
              </div>
            )}
            {(currentStage !== "results" ||
              selectedSteps.some((step) => step.state === "failed")) &&
              stageRows(selectedSteps)}
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
              <ComparisonResults model={model} target={target} />
            )}
            {currentStage !== "results" && logPanel}
          </section>
        </>
      )}
    </article>
  );
}
