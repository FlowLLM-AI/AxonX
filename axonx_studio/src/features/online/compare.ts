import { isRecord } from "../../shared/lib/values";
import type {
  TaskMetadata,
  TaskStepStatus,
  ChildTaskRecord,
} from "../tasks/types";
import type { TaskNode } from "../tasks/tree";

/** Resolve only the latest owned attempt and its exact descendant Tasks. */
export function ownedCompareNodes(
  records: ChildTaskRecord[],
  nodes: TaskNode[],
) {
  const owned = new Set(records.map((r) => `${r.task_id}:${r.started_at}`));
  const result: TaskNode[] = [];
  for (let changed = true; changed;) {
    changed = false;
    for (const node of nodes) {
      if (
        !owned.has(`${node.record.task_id}:${node.record.started_at}`) ||
        result.includes(node)
      )
        continue;
      result.push(node);
      for (const child of node.status?.children || [])
        owned.add(`${child.task_id}:${child.started_at}`);
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
  return (
    Array.isArray(parent.input_params.models) ? parent.input_params.models : []
  )
    .filter(isRecord)
    .map((model) => {
      const name = String(model.task_name);
      const value = outcomes[name];
      const outcome = isRecord(value) ? value : {};
      const roots = records.filter(
        (r) =>
          r.node_name === `${name}-${r.task}` ||
          r.node_name === `${name}-${parent.input_params.trade_time}-${r.task}`,
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
        state = parent.state === "cancelled" ? "cancelled" : "skipped";
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
        (step) => step.name.endsWith(":comparison") && step.state === "skipped",
      );
      const findings: Record<string, unknown>[] = reported.length
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
        provider: String(model.feature_provider || ""),
        outcome,
        roots,
        children,
        steps,
        state,
        finding,
      };
    });
}
export type CompareModel = ReturnType<typeof compareModels>[number];

export function compareStageState(step: TaskStepStatus, parent: TaskMetadata) {
  const state = step.state || "pending";
  return !["running"].includes(parent.state) &&
    ["pending", "waiting", "running"].includes(state)
    ? parent.state === "cancelled"
      ? "cancelled"
      : "skipped"
    : state;
}
export function compareError(error: string) {
  return error.replace(/^ChildTaskError: Child Task '[^']+' failed: /, "");
}
