import { Select } from "../../shared/ui/Select";
import { ModelPicker } from "./ModelPicker";
import { useCallback, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { ReportTabs } from "../../shared/ui/ReportTabs";
import { listTaskStatuses } from "../tasks/api";
import { useRefresh } from "../../shared/hooks/useRefresh";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { TaskSteps } from "../tasks/TaskSteps";
import { TaskRunIssues } from "../tasks/TaskRunIssues";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { Status } from "../tasks/TaskRow";
import type { TaskMetadata } from "../tasks/types";
import { HistoryPreparation } from "./HistoryPreparation";
import { ScopeQuality, type QualitySource } from "./ScopeQuality";
import { CommitProvenance } from "./CommitReport";
import { StockReport } from "./StockReport";
import { loadHistory } from "./api";
import {
  dailyModels,
  dailyCommit,
  modelHistory,
  signalDate,
  dateInput,
  slotLabel,
  collectionSlot,
  aggregateState,
  type ReportNode,
  type SignalHistory,
} from "./daily";

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
      taskId: model.record?.task_id || "",
    })),
  );
  const retained = useRef(new Map<string, SignalHistory>());
  const load = useCallback(
    async (signal: AbortSignal): Promise<SignalHistory[]> => {
      const models = JSON.parse(sources) as {
        modelId: string;
        name: string;
        taskId: string;
      }[];
      const [discovery] = await Promise.allSettled([
        models.some((model) => !model.taskId)
          ? listTaskStatuses(target, signal)
          : Promise.resolve([]),
      ]);
      return Promise.all(
        models.map(async ({ modelId, name, taskId }) => {
          const key = `${target}:${modelId}`;
          try {
            if (!taskId) {
              if (discovery.status === "rejected") throw discovery.reason;
              const candidates = discovery.value.filter(
                (task) =>
                  task.task_type === "inference" &&
                  task.report_kind === "online" &&
                  task.display_name === name,
              );
              if (candidates.length > 1)
                throw new Error(`Ambiguous online history: ${name}`);
              taskId = candidates[0]?.task_id || "";
            }
            const history = taskId
              ? await loadHistory(taskId, target, signal)
              : null;
            signal.throwIfAborted();
            const result = { modelId, taskId, history, error: "" };
            retained.current.set(key, result);
            return result;
          } catch (reason) {
            signal.throwIfAborted();
            const previous = retained.current.get(key);
            return {
              modelId,
              taskId: taskId || previous?.taskId || "",
              history:
                !taskId || taskId === previous?.taskId
                  ? previous?.history || null
                  : null,
              error: String(reason),
            };
          }
        }),
      );
    },
    [sources, target],
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
          record.run_id === node.record.run_id &&
          record.task_id === node.record.task_id,
      ) && node.status?.task_type === "etl",
  );
  const hasEtl = publicSteps.length > 0 || publicNodes.length > 0;
  const statesAt = (slot: string) => {
    const entries = planned.filter((model) => model.slot === slot);
    if (!live)
      return entries.length &&
        entries.every((model) => dailyCommit(model, histories, date))
        ? "done"
        : "unavailable";
    if (entries.length && entries.every((model) => model.state === "missed"))
      return "missed";
    const activityStates = [
      ...collection
        .filter((step) => collectionSlot(step.name) === slot)
        .map((step) => step.state),
      ...entries.map((model) => (model.error ? "failed" : model.state)),
    ];
    const historyStates = parent.steps
      .filter(
        (step) => step.group === "history" && step.name.endsWith(`-${slot}`),
      )
      .map((step) => step.state);
    const state = aggregateState([...activityStates, ...historyStates]);
    if (state === "running" && !activityStates.includes("running"))
      return "preparing";
    if (
      state === "done" &&
      entries.length &&
      !entries.every((model) => dailyCommit(model, histories, date))
    )
      return "incomplete";
    return state;
  };
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
    <span className={`online-status status-${state}`}>
      {t(
        `onlineWorkbench.states.${state}`,
        t(`onlinePipeline.status.${state}`, state),
      )}
    </span>
  );
  const emptyRun = <p className="empty-state">{t("onlineWorkbench.noRun")}</p>;
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
          (step.phase ||
            step.completed != null ||
            Object.keys(step.files || {}).length ||
            Object.keys(step.metrics || {}).length)),
    );
    if (!live) return emptyRun;
    if (!useful.length && !model?.error) return null;
    return (
      <section className="pipeline-model-content">
        {model?.error && (
          <p className="error-state" role="alert">
            {t(`onlinePipeline.reasons.${model.error}`, model.error)}
          </p>
        )}
        {useful.length > 0 && (
          <TaskSteps
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
        <TaskSteps
          filesOnly
          task={parent}
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
        <TaskSteps task={parent} target={target} steps={otherPreparation} />
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
                    <TaskSteps
                      filesOnly
                      task={parent}
                      target={target}
                      steps={publicSteps}
                    />
                    {publicNodes.map((node) => (
                      <section
                        key={node.record.run_id}
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
                        <TaskSteps
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
              {showStages([...scores, ...publication], !!commit)}
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
                <p className="empty-state" role="status">
                  {loading ? t("shell.loading") : t("onlineWorkbench.noSignal")}
                </p>
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
      {live && <TaskRunIssues nodes={nodes} />}
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
          <button type="button" onClick={() => void refreshAll()}>
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
                  {scopeStatus(statesAt(slot))}
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
            <ModelPicker
              key={scope}
              models={slotModels.map((model) => model.name)}
              value={modelName}
              onChange={setModel}
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

function DailyLogs({
  parent,
  nodes,
  scope,
  modelName,
  target,
  onOpenTask,
}: {
  parent: TaskMetadata;
  nodes: ReportNode[];
  scope: string;
  modelName?: string;
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState("");
  const inference = dailyModels(parent, nodes).filter(
    (model) =>
      scope === "data" || (model.slot === scope && model.name === modelName),
  );
  const roots = inference.flatMap((model) =>
    model.record ? [model.record] : [],
  );
  if (scope === "data")
    roots.push(
      ...parent.children.filter((record) =>
        record.task_id?.startsWith("composite#"),
      ),
    );
  const included = new Set(
    roots.map((record) => `${record.task_id}:${record.run_id}`),
  );
  // readTaskChildren returns parents before descendants, preserving exact Run ownership.
  for (const node of nodes)
    if (included.has(`${node.record.task_id}:${node.record.run_id}`))
      for (const child of node.status?.children || [])
        included.add(`${child.task_id}:${child.run_id}`);
  const tasks =
    scope === "data"
      ? [
          parent,
          ...nodes
            .filter(
              (node) =>
                !included.has(`${node.record.task_id}:${node.record.run_id}`),
            )
            .flatMap((node) => (node.status ? [node.status] : [])),
        ]
      : inference.flatMap((model) =>
          model.node?.status ? [model.node.status] : [],
        );
  const current = tasks.find((task) => task.run_id === selected) || tasks[0];
  const sourceLabel = (task: TaskMetadata) =>
    task === parent
      ? t("onlinePipeline.chainLog")
      : `${t(`taskGraph.kinds.${task.task_type}`, task.task_type)} · ${String(task.input_params.task_name || task.reg_name)}`;
  const toolbar = (
    <div className="daily-log-source">
      {tasks.length > 1 ? (
        <label className="pipeline-log-source">
          {t("onlinePipeline.logSource")}
          <Select
            value={current?.run_id || ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {tasks.map((task) => (
              <option key={task.run_id} value={task.run_id}>
                {sourceLabel(task)}
                {tasks.some(
                  (other) =>
                    other !== task && sourceLabel(other) === sourceLabel(task),
                ) && ` · ${task.reg_name} · ${task.run_id}`}
              </option>
            ))}
          </Select>
        </label>
      ) : (
        current && (
          <span className="daily-log-caption" title={current.task_id}>
            {sourceLabel(current)}
          </span>
        )
      )}
      {current && (
        <button
          type="button"
          className="secondary-button"
          onClick={() => onOpenTask(current.task_id)}
        >
          {t("onlinePipeline.openTask")}
        </button>
      )}
    </div>
  );
  return current ? (
    <TaskLogPanel
      key={`${target}:${current.task_id}:${current.run_id}`}
      task={current}
      target={target}
      toolbar={toolbar}
    />
  ) : (
    <p className="empty-state">{t("onlinePipeline.pending")}</p>
  );
}
