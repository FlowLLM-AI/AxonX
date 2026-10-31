import type { ChildTaskRecord, TaskMetadata } from "../../shared/api/contracts";
import type { TaskStepStatus } from "../../shared/api/event";
import { isRecord } from "../../shared/lib/values";
import type { TaskNode } from "../tasks/tree";
import { slotLabel } from "./daily";

/** Resolve only the latest owned attempt and its exact descendant Tasks. */
export function ownedCompareNodes(
  records: ChildTaskRecord[],
  nodes: TaskNode[],
) {
  const owned = new Set(
    records.map((r) => `${r.child_task_id}:${r.started_at}`),
  );
  const result: TaskNode[] = [];
  for (let changed = true; changed;) {
    changed = false;
    for (const node of nodes) {
      if (
        !owned.has(`${node.record.child_task_id}:${node.record.started_at}`) ||
        result.includes(node)
      )
        continue;
      result.push(node);
      for (const child of node.status?.children || [])
        owned.add(`${child.child_task_id}:${child.started_at}`);
      changed = true;
    }
  }
  return result;
}

export function compareModels(parent: TaskMetadata, nodes: TaskNode[]) {
  const outcomes = isRecord(parent.output_params.models)
    ? parent.output_params.models
    : {};
  const records = [
    ...new Map(parent.children.map((r) => [r.node_name, r])).values(),
  ];
  const schedule = isRecord(parent.input_params.models)
    ? parent.input_params.models
    : {};
  return Object.entries(schedule)
    .sort(([a], [b]) => a.localeCompare(b))
    .flatMap(([slot, entries]) =>
      (Array.isArray(entries) ? entries : []).filter(isRecord).map((model) => {
        const taskName = String(model.task_name);
        const name = `${taskName}-${slot}`;
        const label = `${taskName} · ${slotLabel(slot)}`;
        const slotOutcomes = isRecord(outcomes[slot]) ? outcomes[slot] : {};
        const value = slotOutcomes[taskName];
        const outcome = isRecord(value) ? value : {};
        const registrations = {
          etl: "a_stock_history",
          prediction: isRecord(model.predict)
            ? String(model.predict.reg_name)
            : "",
          portfolio: isRecord(model.portfolio)
            ? String(model.portfolio.reg_name)
            : "",
          comparison: isRecord(model.compare)
            ? String(model.compare.reg_name)
            : "",
        };
        const roles = Object.fromEntries(
          Object.entries(registrations).map(([role, registration]) => [
            role,
            records.find((r) => r.node_name === `${name}-${registration}`),
          ]),
        );
        const roots = Object.values(roles).filter(
          (record): record is ChildTaskRecord => !!record,
        );
        const children = ownedCompareNodes(roots, nodes);
        const steps = parent.steps.filter((step) => step.group === name);
        let state = String(outcome.status || "pending");
        if (
          steps.some((step) => step.state === "failed") ||
          roots.some((r) => r.state === "failed") ||
          children.some((node) => node.status?.state === "failed")
        )
          state = "failed";
        else if (
          !["running"].includes(parent.state) &&
          ["pending", "waiting", "running"].includes(state)
        )
          state = "skipped";
        else if (steps.some((step) => step.state === "running"))
          state = "running";
        const comparison = isRecord(outcome.comparison)
          ? outcome.comparison
          : null;
        const reported = children
          .flatMap((n) =>
            Array.isArray(n.status?.output_params.comparisons)
              ? n.status.output_params.comparisons
              : [],
          )
          .filter(isRecord);
        const skipped = steps.find(
          (step) =>
            step.name.endsWith(":comparison") && step.state === "skipped",
        );
        const findings: Record<string, unknown>[] =
          comparison && isRecord(comparison.artifacts)
            ? [comparison]
            : reported.length
              ? reported
              : comparison
                ? [comparison]
                : skipped
                  ? [{ status: "skipped", reason: skipped.error }]
                  : [];
        const finding =
          findings.find(
            (r) => r.status !== "consistent" && r.status !== "skipped",
          ) || findings[0];
        return {
          name,
          label,
          provider: isRecord(model.train) ? String(model.train.reg_name) : "",
          outcome,
          roots,
          roles,
          children,
          steps,
          state,
          finding,
          taskId: parent.task_id,
          startedAt: parent.started_at,
        };
      }),
    );
}
export type CompareModel = ReturnType<typeof compareModels>[number];

export function compareStageState(step: TaskStepStatus, parent: TaskMetadata) {
  const state = step.state || "pending";
  return !["running"].includes(parent.state) &&
    ["pending", "waiting", "running"].includes(state)
    ? "skipped"
    : state;
}
export function compareError(error: string) {
  return error.replace(/^ChildTaskError: Child Task '[^']+' failed: /, "");
}
