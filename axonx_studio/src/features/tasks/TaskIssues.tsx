import { useTranslation } from "react-i18next";
import type { TaskNode } from "./tree";

/** Missing overwritten Task metadata is distinct from a request failure. */
export function TaskIssues({ nodes }: { nodes: TaskNode[] }) {
  const { t } = useTranslation();
  const replaced = nodes.filter((node) => node.issue === "replaced");
  const errors = new Map<string, TaskNode[]>();
  for (const node of nodes) {
    if (!node.error || node.issue === "replaced") continue;
    errors.set(node.error, [...(errors.get(node.error) || []), node]);
  }
  return (
    <>
      {replaced.length > 0 && (
        <div className="task-execution-notice" role="status">
          <p>
            {t("onlinePipeline.replacedChildren", { count: replaced.length })}
          </p>
          <small>
            {[...new Set(replaced.map((node) => node.record.node_name))].join(
              " · ",
            )}
          </small>
        </div>
      )}
      {[...errors].map(([message, affected]) => (
        <p className="error-state" role="alert" key={message}>
          {message}
          {affected.length > 1 && <small> · {affected.length}</small>}
        </p>
      ))}
    </>
  );
}
