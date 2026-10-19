import { ReportTabs } from "../../shared/ui/ReportTabs";
import { useTranslation } from "react-i18next";
import { TaskSteps } from "./TaskSteps";
import { Status } from "./TaskRow";
import type { TaskNode } from "./tree";
import type { ChildTaskRecord } from "./types";

export function TaskChildren({
  target,
  records,
  nodes,
  onOpenTask,
  ancestors = [],
  showOutput = false,
}: {
  target?: string;
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
            <section className="task-child" key={record.run_id}>
              <header>
                {record.node_name} · <Status state={record.state} />
              </header>
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
                  {showOutput ? (
                    <ReportTabs
                      tabs={[
                        {
                          id: "steps",
                          label: t("onlinePipeline.stageDetails"),
                          content: (
                            <TaskSteps
                              target={target}
                              compact
                              task={status}
                              steps={status.steps}
                            />
                          ),
                        },
                        {
                          id: "result",
                          label: t("operations.result"),
                          content: (
                            <pre>
                              {JSON.stringify(status.output_params, null, 2)}
                            </pre>
                          ),
                        },
                      ]}
                    />
                  ) : (
                    <TaskSteps
                      target={target}
                      compact
                      task={status}
                      steps={status.steps}
                    />
                  )}
                  <TaskChildren
                    target={target}
                    records={status.children}
                    showOutput={showOutput}
                    nodes={nodes}
                    onOpenTask={onOpenTask}
                    ancestors={[...ancestors, record.run_id]}
                  />
                </>
              )}
            </section>
          );
        })}
    </>
  );
}
