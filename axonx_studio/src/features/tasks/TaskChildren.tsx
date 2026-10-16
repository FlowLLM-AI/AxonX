import { useTranslation } from "react-i18next";
import { TaskSteps } from "./TaskSteps";
import { Status } from "./TaskRow";
import type { TaskNode } from "./tree";
import type { ChildTaskRecord } from "./types";

export function TaskChildren({
  records,
  nodes,
  onOpenTask,
  ancestors = [],
  showOutput = false,
}: {
  records: ChildTaskRecord[];
  nodes: TaskNode[];
  onOpenTask: (id: string) => void;
  ancestors?: string[];
  showOutput?: boolean;
}) {
  const { t } = useTranslation();
  const latest = [
    ...new Map(records.map((record) => [record.node_name, record])).values(),
  ];
  return (
    <>
      {latest
        .filter((record) => !ancestors.includes(record.run_id))
        .map((record) => {
          const node = nodes.find(
            (node) =>
              node.record.task_id === record.task_id &&
              node.record.run_id === record.run_id,
          );
          const status = node?.status;
          return (
            <details key={record.run_id} open={record.state === "running"}>
              <summary>
                {record.node_name} · <Status state={record.state} />
              </summary>
              {(record.error || node?.error) && (
                <p className="error-state">{record.error || node?.error}</p>
              )}
              {status && (
                <>
                  <button
                    className="secondary-button"
                    onClick={() => onOpenTask(status.task_id)}
                  >
                    {t("onlinePipeline.openTask")}
                  </button>
                  <TaskSteps compact steps={status.steps} />
                  {showOutput && (
                    <details>
                      <summary>{t("operations.result")}</summary>
                      <pre>{JSON.stringify(status.output_params, null, 2)}</pre>
                    </details>
                  )}
                  <TaskChildren
                    records={status.children}
                    showOutput={showOutput}
                    nodes={nodes}
                    onOpenTask={onOpenTask}
                    ancestors={[...ancestors, record.run_id]}
                  />
                </>
              )}
            </details>
          );
        })}
    </>
  );
}
