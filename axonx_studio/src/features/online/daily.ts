import type { TaskMetadata } from "../tasks/types";
import type { TaskNode } from "../tasks/tree";
import {
  activeCommits,
  type OnlineHistory,
  type StockOnlineReport,
} from "./report";

export type ReportNode = TaskNode & { report?: StockOnlineReport | null };
export type SignalHistory = {
  modelId: string;
  taskId: string;
  history: OnlineHistory | null;
  error: string;
};

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
              child.task_id?.startsWith("inference#") &&
              child.node_name === `${name}-${slot}-${child.task}`,
          );
        const node = nodes.find(
          (item) =>
            item.record.task_id === record?.task_id &&
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
export type DailyModel = ReturnType<typeof dailyModels>[number];

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

export const signalDate = (value: string) => value.replaceAll("-", "");
export const dateInput = (value: string) =>
  `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
export const slotLabel = (value: string) =>
  `${value.slice(0, 2)}:${value.slice(2)}`;

/** Collection before/bar records belong to the same signal time. */
export function collectionSlot(name: string) {
  return /^(?:collection:)?(\d{4})_(?:before|bar)$/.exec(name)?.[1];
}

export function aggregateState(states: (string | null | undefined)[]) {
  const values = states.filter(Boolean);
  if (
    values.some((state) =>
      ["failed", "missed", "incomplete", "cancelled"].includes(state!),
    )
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
