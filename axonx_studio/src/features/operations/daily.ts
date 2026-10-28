import type { TaskMetadata } from "../../shared/api/contracts";
import { compactDate } from "../../shared/lib/format";
import { listTaskStatuses } from "../tasks/api";
import type { TaskNode } from "../tasks/tree";
import { loadHistory } from "./api";
import {
  activeCommits,
  type OnlineHistory,
  type StockOnlineReport,
} from "./report";

export type ReportNode = TaskNode & { report?: StockOnlineReport | null };
type SignalHistory = {
  modelId: string;
  taskId: string;
  history: OnlineHistory | null;
  error: string;
};

/** History progress identifies the child role independently of its Task type. */
export function historyTaskRecords(parent: TaskMetadata) {
  const names = parent.steps
    .filter((step) => step.group === "history")
    .map((step) => step.name.replace(/^history:/, ""));
  return [
    ...new Map(
      parent.children
        .filter((record) =>
          names.some(
            (name) => record.node_name === `${name}-${record.reg_name}`,
          ),
        )
        .map((record) => [record.node_name, record]),
    ).values(),
  ];
}

export function dailyModels(parent: TaskMetadata, nodes: ReportNode[]) {
  const plan = (parent.input_params.models || {}) as Record<
    string,
    { task_name: string }[]
  >;
  return Object.entries(plan)
    .sort(([a], [b]) => a.localeCompare(b))
    .flatMap(([slot, entries]) =>
      entries.map(({ task_name: name }) => {
        const record = [...parent.children]
          .reverse()
          .find(
            (child) =>
              child.child_task_id?.startsWith("inference#") &&
              child.node_name === `${name}-${slot}-${child.reg_name}`,
          );
        const node = nodes.find(
          (item) =>
            item.record.child_task_id === record?.child_task_id &&
            item.record.started_at === record?.started_at,
        );
        const outcomes = parent.output_params.models as
          Record<string, Record<string, unknown>> | undefined;
        const outcome = (outcomes?.[slot]?.[name] || outcomes?.[slot]) as
          { status?: string; error?: string; reason?: string } | undefined;
        return {
          id: `${slot}:${name}`,
          slot,
          name,
          record,
          node,
          state:
            record?.state ||
            outcome?.status ||
            (["running"].includes(parent.state) ? "pending" : "skipped"),
          error:
            record?.error ||
            outcome?.error ||
            outcome?.reason ||
            node?.error ||
            "",
        };
      }),
    );
}
type DailyModel = ReturnType<typeof dailyModels>[number];

export function modelHistory(model: DailyModel, histories: SignalHistory[]) {
  return histories.find((item) => item.modelId === model.id);
}

export function dailyCommit(
  model: DailyModel,
  histories: SignalHistory[],
  date: string,
) {
  const history = modelHistory(model, histories)?.history;
  const commits = history
    ? activeCommits(history)
    : model.node?.report
      ? [model.node.report.commit]
      : [];
  return commits.find(
    (commit) => commit.trade_date === date && commit.trade_time === model.slot,
  );
}

export const slotLabel = (value: string) =>
  `${value.slice(0, 2)}:${value.slice(2)}`;

/** Collection before/bar records belong to the same signal time. */
export function collectionSlot(name: string) {
  return /^(?:collection:)?(\d{4})_(?:before|bar)$/.exec(name)?.[1];
}

export function aggregateState(states: (string | null | undefined)[]) {
  const values = states.filter(Boolean);
  if (
    values.some((state) => ["failed", "missed", "incomplete"].includes(state!))
  )
    return "failed";
  if (values.some((state) => state === "running")) return "running";
  if (
    !values.length ||
    values.some((state) => ["pending", "waiting"].includes(state!))
  )
    return "pending";
  if (values.every((state) => state === "skipped")) return "skipped";
  return "done";
}

interface HistorySource {
  modelId: string;
  name: string;
  taskId: string;
}
/** Retain each model's last good history independently when discovery or refresh fails. */
export class SignalHistoryStore {
  private readonly retained = new Map<string, SignalHistory>();
  constructor(private readonly target?: string) {}
  async load(
    models: HistorySource[],
    signal: AbortSignal,
  ): Promise<SignalHistory[]> {
    const { target, retained } = this;

    const [discovery] = await Promise.allSettled([
      models.some((model) => !model.taskId)
        ? listTaskStatuses({ target, signal })
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
            ? await loadHistory(taskId, { target, signal })
            : null;
          signal.throwIfAborted();
          const result = { modelId, taskId, history, error: "" };
          retained.set(key, result);
          return result;
        } catch (reason) {
          signal.throwIfAborted();
          const previous = retained.get(key);
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
  }
}

export function dailySlotState(
  parent: TaskMetadata,
  planned: DailyModel[],
  histories: SignalHistory[],
  date: string,
  slot: string,
) {
  const live =
    date === compactDate(String(parent.input_params.trade_date || ""));
  const collection = parent.steps.filter((step) => step.group === "collection");

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
  const historySteps = parent.steps.filter(
    (step) => step.group === "history" && step.name.endsWith(`-${slot}`),
  );
  const state = aggregateState([
    ...activityStates,
    ...historySteps.map((step) => step.state),
  ]);
  if (state === "pending" && !["running"].includes(parent.state))
    return "incomplete";
  if (state === "running" && !activityStates.includes("running"))
    return "preparing";
  if (
    state === "done" &&
    entries.length &&
    !entries.every((model) => dailyCommit(model, histories, date))
  )
    return "incomplete";
  if (
    state === "pending" &&
    entries.length &&
    entries.every((model) =>
      historySteps.some(
        (step) =>
          step.name === `history:${model.name}-${slot}` &&
          step.state === "done",
      ),
    )
  )
    return "ready";
  return state;
}
