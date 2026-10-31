import { useCallback, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "../../shared/api/contracts";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { dateInput, compactDate as signalDate } from "../../shared/lib/format";
import { selectOptions } from "../../shared/lib/values";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { ReportTabs } from "../../shared/ui/ReportTabs";
import { Picker } from "../../shared/ui/Select";
import { TaskIssues } from "../tasks/TaskIssues";
import { Status } from "../tasks/TaskRow";
import { CommitProvenance } from "./CommitReport";
import {
  aggregateState,
  collectionSlot,
  dailyCommit,
  dailyModels,
  dailySlotState,
  modelHistory,
  SignalHistoryStore,
  slotLabel,
  type ReportNode,
} from "./daily";
import { HistoryPreparation } from "./HistoryPreparation";
import { DailyLogs } from "./PipelineLogs";
import { PipelineSteps } from "./PipelineSteps";
import { ScopeQuality, type QualitySource } from "./ScopeQuality";
import { StockReport } from "./StockReport";

export function OnlineWorkbench({
  parent,
  refreshedAt,
  error,
  nodes,
  target,
  onOpenTask,
}: {
  parent: TaskMetadata;
  refreshedAt: string;
  error: string;
  nodes: ReportNode[];
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const prefix = useId();
  const planned = dailyModels(parent, nodes);
  const sources = JSON.stringify(
    planned.map((model) => ({
      modelId: model.id,
      name: `${model.name}-${model.slot}`,
      taskId: model.report?.commit.task_id || model.record?.child_task_id || "",
      published: !!model.report,
    })),
  );
  const historiesStore = useMemo(
    () => new SignalHistoryStore(target),
    [target],
  );
  const load = useCallback(
    (signal: AbortSignal) => historiesStore.load(JSON.parse(sources), signal),
    [historiesStore, sources],
  );
  const { data, loading, reload } = useAsyncResource(load);
  const refreshAll = useRefresh(reload);
  const histories = data || [];
  const runDate = signalDate(String(parent.input_params.trade_date || ""));
  const [selectedDate, setDate] = useState("");
  const date = selectedDate || runDate;
  const live = date === runDate;
  const [selectedScope, setScope] = useState("data");
  const [dataStage, setDataStage] = useState("collection");
  const [slotStage, setSlotStage] = useState("collection");
  const [selectedModel, setModel] = useState("");
  const collection = parent.steps.filter((step) => step.group === "collection");
  const slots = [
    ...new Set([
      ...planned.map((model) => model.slot),
      ...(live
        ? collection.flatMap((step) => collectionSlot(step.name) || [])
        : []),
      ...histories.flatMap(
        (item) =>
          item.history?.commits
            .filter((commit) => commit.trade_date === date)
            .map((commit) => commit.trade_time) || [],
      ),
    ]),
  ].sort();
  const scope =
    selectedScope === "data" || slots.includes(selectedScope)
      ? selectedScope
      : "data";
  const isData = scope === "data";
  const slotModels = planned.filter((model) => model.slot === scope);
  const model =
    slotModels.find((model) => model.name === selectedModel) || slotModels[0];
  const modelName = model?.name || "";
  const commit = model && dailyCommit(model, histories, date);
  const history = model && modelHistory(model, histories);
  const sharedCollection = collection.filter(
    (step) => !collectionSlot(step.name),
  );
  const publicSteps = parent.steps.filter(
    (step) =>
      !["collection", "history"].includes(step.group || "") &&
      !collectionSlot(step.name) &&
      /(?:^|:)etl(?:$|:)/.test(`${step.group}:${step.name}`),
  );
  const otherPreparation = parent.steps.filter(
    (step) =>
      step.parent &&
      !["collection", "history"].includes(step.group || "") &&
      !publicSteps.includes(step),
  );
  const publicNodes = nodes.filter(
    (node) =>
      parent.children.some(
        (record) =>
          record.started_at === node.record.started_at &&
          record.child_task_id === node.record.child_task_id,
      ) && node.status?.task_type === "etl",
  );
  const hasEtl = publicSteps.length > 0 || publicNodes.length > 0;
  const dataState = live
    ? aggregateState([
        ...sharedCollection.map((step) => step.state),
        ...publicSteps.map((step) => step.state),
        ...otherPreparation.map((step) => step.state),
        ...publicNodes.map((node) => node.record.state),
      ])
    : "unavailable";
  const stamp = (value: string) =>
    new Date(value).toLocaleString(
      i18n?.resolvedLanguage === "zh" ? "zh-CN" : "en-US",
      { timeZone: "Asia/Shanghai", hour12: false },
    );
  const status = (state: string) => (
    <span className={`online-status status-${state}`}>
      {state === "unavailable"
        ? t("onlineWorkbench.unavailable")
        : t(`onlinePipeline.status.${state}`, state)}
    </span>
  );
  const scopeStatus = (state: string) => (
    <span
      className={`online-status status-${state}`}
      title={t(`onlineWorkbench.stateHints.${state}`, "") || undefined}
    >
      {t(
        `onlineWorkbench.states.${state}`,
        t(`onlinePipeline.status.${state}`, state),
      )}
    </span>
  );
  const emptyRun = (
    <p className="empty-state">{t("onlineWorkbench.noTaskRecord")}</p>
  );
  const emptyStage = (
    <p className="empty-state">{t("onlinePipeline.pending")}</p>
  );
  const stages = model?.node?.status?.steps.filter((step) => step.parent) || [];
  const features = stages.filter((step) =>
    ["initialization", "feature", "etl"].includes(step.name),
  );
  const scores = stages.filter(
    (step) =>
      !features.includes(step) &&
      !["portfolio", "publication"].includes(step.name),
  );
  const publication = stages.filter((step) =>
    ["portfolio", "publication"].includes(step.name),
  );
  const showStages = (steps: typeof stages, published = false) => {
    const useful = steps.filter(
      (step) =>
        !["done", "succeeded", "skipped"].includes(step.state || "") ||
        step.error ||
        (!published &&
          ((step.completed != null && step.total !== 1) ||
            Object.keys(step.files || {}).length ||
            Object.keys(step.metrics || {}).length)),
    );
    const modelError = model?.error;
    const showError =
      modelError &&
      modelError !== model.node?.error &&
      !useful.some((step) => step.error === modelError);
    if (!useful.length && !showError) return null;
    return (
      <section className="pipeline-model-content">
        {showError && (
          <p className="error-state" role="alert">
            {t(`onlinePipeline.reasons.${modelError}`, modelError)}
          </p>
        )}
        {useful.length > 0 && (
          <PipelineSteps
            filesOnly
            task={model?.node?.status || undefined}
            target={target}
            compact
            steps={useful}
          />
        )}
      </section>
    );
  };
  const collectionOptions = parent.input_params.collection as
    { coverage_grace_seconds?: number; coverage_ratio?: number } | undefined;
  const collectionPanel = !live ? (
    emptyRun
  ) : (
    <>
      {!isData &&
        typeof collectionOptions?.coverage_grace_seconds === "number" &&
        typeof collectionOptions.coverage_ratio === "number" && (
          <p className="muted">
            {t("onlineWorkbench.coveragePolicy", {
              seconds: collectionOptions.coverage_grace_seconds,
              threshold: (collectionOptions.coverage_ratio * 100).toFixed(1),
            })}
          </p>
        )}
      {(isData
        ? sharedCollection
        : collection.filter((step) => collectionSlot(step.name) === scope)
      ).length ? (
        <PipelineSteps
          filesOnly
          target={target}
          steps={
            isData
              ? sharedCollection
              : collection.filter((step) => collectionSlot(step.name) === scope)
          }
        />
      ) : (
        emptyStage
      )}
      {isData && otherPreparation.length > 0 && (
        <PipelineSteps task={parent} target={target} steps={otherPreparation} />
      )}
    </>
  );
  const dates = [
    ...new Set([
      runDate,
      ...histories.flatMap(
        (item) =>
          item.history?.commits.map((commit) => commit.trade_date) || [],
      ),
    ]),
  ]
    .sort()
    .reverse();
  const qualitySources: QualitySource[] = isData
    ? ["snapshot"]
    : ["before", "bar", "model"];
  const qualityTabs = qualitySources.map((source) => ({
    id: `quality-${source}`,
    label: t(`onlineWorkbench.qualitySources.${source}`),
    lazy: true,
    content: (
      <ScopeQuality
        parent={parent}
        scope={scope}
        live={live}
        commit={commit}
        target={target}
        source={source}
      />
    ),
  }));
  const resultStages =
    live && showStages([...scores, ...publication], !!commit);
  const tabs = isData
    ? [
        {
          id: "collection",
          label: t("onlineWorkbench.baseCollection"),
          content: collectionPanel,
        },
        ...(hasEtl
          ? [
              {
                id: "etl",
                label: t("onlineWorkbench.sharedEtl"),
                content: !live ? (
                  emptyRun
                ) : (
                  <>
                    <PipelineSteps
                      filesOnly
                      target={target}
                      steps={publicSteps}
                    />
                    {publicNodes.map((node) => (
                      <section
                        key={node.record.child_task_id || node.record.node_name}
                        className="pipeline-step"
                      >
                        <header>
                          <strong>{node.record.node_name}</strong>
                          {status(node.record.state)}
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => onOpenTask(node.status!.task_id)}
                          >
                            {t("onlinePipeline.openTask")}
                          </button>
                        </header>
                        <PipelineSteps
                          filesOnly
                          task={node.status!}
                          target={target}
                          steps={node.status!.steps.filter(
                            (step) => step.parent,
                          )}
                        />
                      </section>
                    ))}
                  </>
                ),
              },
            ]
          : []),
        ...qualityTabs,
        {
          id: "logs",
          label: t("taskDetail.logs"),
          lazy: true,
          content: !live ? (
            emptyRun
          ) : (
            <DailyLogs
              parent={parent}
              nodes={nodes}
              scope="data"
              target={target}
              onOpenTask={onOpenTask}
            />
          ),
        },
      ]
    : [
        {
          id: "collection",
          label: t("onlinePipeline.collection"),
          content: collectionPanel,
        },
        {
          id: "preparation",
          label: t("onlineWorkbench.modelPreparation"),
          lazy: true,
          content: !live ? (
            emptyRun
          ) : (
            <>
              <HistoryPreparation
                parent={parent}
                nodes={nodes}
                target={target}
                modelName={modelName}
                slot={scope}
                onOpenTask={onOpenTask}
              />
              {showStages(features)}
              {commit && <CommitProvenance commit={commit} />}
              {!features.length &&
                !commit &&
                !parent.steps.some(
                  (step) =>
                    step.group === "history" &&
                    step.name === `history:${modelName}-${scope}`,
                ) &&
                !model?.error &&
                emptyStage}
            </>
          ),
        },
        {
          id: "results",
          label: t("onlineWorkbench.predictionResults"),
          lazy: true,
          content: (
            <>
              {resultStages}
              {commit ? (
                <StockReport
                  key={`${target}:${model.id}:${date}`}
                  report={{ kind: "stock_online", commit }}
                  target={target}
                  runtime={null}
                  flat
                  selection={{
                    date,
                    slot: scope,
                    history: history?.history || null,
                  }}
                />
              ) : (
                !resultStages && (
                  <p className="empty-state" role="status">
                    {loading
                      ? t("shell.loading")
                      : t("onlineWorkbench.noSignal")}
                  </p>
                )
              )}
            </>
          ),
        },
        ...qualityTabs,
        {
          id: "logs",
          label: t("taskDetail.logs"),
          lazy: true,
          content: !live ? (
            emptyRun
          ) : (
            <DailyLogs
              parent={parent}
              nodes={nodes}
              scope={scope}
              modelName={modelName}
              target={target}
              onOpenTask={onOpenTask}
            />
          ),
        },
      ];
  const runError =
    live &&
    !(
      parent.state === "failed" &&
      /^Task exited with code -?\d+\.?$/.test(parent.error?.trim() || "")
    )
      ? parent.error
      : "";
  return (
    <article className="online-report pipeline-report online-daily-workbench">
      <ReplicaNotice replica={parent.replica} state={parent.state} />
      <header>
        <div>
          <p className="eyebrow">{t("onlineWorkbench.title")}</p>
          <div className="online-task-title">
            <h2>{String(parent.input_params.task_name || parent.reg_name)}</h2>
            {live ? (
              <Status state={parent.state} />
            ) : (
              <span className="online-status">
                {t("onlineWorkbench.historical")}
              </span>
            )}
          </div>
        </div>
        <label className="online-date-filter">
          {t("onlineWorkbench.date")}
          <input
            type="date"
            aria-label={t("onlineWorkbench.date")}
            list={`${prefix}-dates`}
            value={dateInput(date)}
            onChange={(event) => {
              if (event.target.value) {
                setDate(signalDate(event.target.value));
              }
            }}
          />
        </label>
        <datalist id={`${prefix}-dates`}>
          {dates.map((value) => (
            <option key={value} value={dateInput(value)} />
          ))}
        </datalist>
        <button
          type="button"
          className="secondary-button"
          onClick={() => onOpenTask(parent.task_id)}
        >
          {t("onlinePipeline.openTask")}
        </button>
      </header>
      {(error || runError) && (
        <div className="error-state" role="alert">
          {error || runError}
        </div>
      )}
      {live && <TaskIssues nodes={nodes} />}
      <div className="online-day-summary">
        <span>
          {t("onlineWorkbench.submitted")}{" "}
          <strong>
            {
              slots.filter(
                (slot) =>
                  planned.some((model) => model.slot === slot) &&
                  planned
                    .filter((model) => model.slot === slot)
                    .every((model) => dailyCommit(model, histories, date)),
              ).length
            }{" "}
            {live && ` / ${slots.length}`}
          </strong>
        </span>
        <small>
          {t("onlineWorkbench.updated")} {stamp(refreshedAt)} ·{" "}
          {t("onlinePipeline.refreshHint")} · {t("onlineWorkbench.timezone")}
        </small>
      </div>
      {histories.some((item) => item.error) && (
        <div className="online-warning" role="status">
          {t("onlineWorkbench.historyError")}
          <button
            type="button"
            className="secondary-button"
            onClick={() => void refreshAll()}
          >
            {t("retry")}
          </button>
        </div>
      )}
      <div className="online-time-navigation">
        <ReportTabs
          selected={scope}
          onSelected={setScope}
          panelId={`${prefix}-scope-panel`}
          separateFirst
          ariaLabel={t("onlineWorkbench.scopeLabel")}
          tabs={[
            {
              id: "data",
              label: (
                <>
                  <strong>{t("onlineWorkbench.data")}</strong>
                  {scopeStatus(dataState)}
                </>
              ),
            },
            ...slots.map((slot) => ({
              id: slot,
              label: (
                <>
                  <strong>{slotLabel(slot)}</strong>
                  {scopeStatus(
                    dailySlotState(parent, planned, histories, date, slot),
                  )}
                </>
              ),
            })),
          ]}
        />
      </div>
      <section
        id={`${prefix}-scope-panel`}
        role="tabpanel"
        aria-label={isData ? t("onlineWorkbench.data") : slotLabel(scope)}
        className={`online-scope-content${isData ? " preparation" : ""}`}
      >
        {!isData && (
          <div className="online-scope-toolbar">
            <Picker
              key={scope}
              value={modelName}
              onChange={setModel}
              label={t("onlineWorkbench.model")}
              className="online-model-picker"
              options={selectOptions(slotModels.map((model) => model.name))}
            />
          </div>
        )}
        <ReportTabs
          ariaLabel={t("onlineWorkbench.stageLabel")}
          selected={isData ? dataStage : slotStage}
          onSelected={isData ? setDataStage : setSlotStage}
          tabs={tabs}
        />
      </section>
    </article>
  );
}
