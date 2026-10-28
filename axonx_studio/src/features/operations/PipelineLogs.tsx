import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "../../shared/api/contracts";
import { Select } from "../../shared/ui/Select";
import { TaskLogPanel } from "../tasks/TaskLogPanel";
import { dailyModels, historyTaskRecords, type ReportNode } from "./daily";

export function DailyLogs({
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
  if (scope === "data") roots.push(...historyTaskRecords(parent));
  const included = new Set(
    roots.map((record) => `${record.child_task_id}:${record.started_at}`),
  );
  // readTaskChildren returns parents before descendants, preserving recorded child start times.
  for (const node of nodes)
    if (included.has(`${node.record.child_task_id}:${node.record.started_at}`))
      for (const child of node.status?.children || [])
        included.add(`${child.child_task_id}:${child.started_at}`);
  const tasks =
    scope === "data"
      ? [
          parent,
          ...nodes
            .filter(
              (node) =>
                !included.has(
                  `${node.record.child_task_id}:${node.record.started_at}`,
                ),
            )
            .flatMap((node) => (node.status ? [node.status] : [])),
        ]
      : inference.flatMap((model) =>
          model.node?.status ? [model.node.status] : [],
        );
  const current = tasks.find((task) => task.task_id === selected) || tasks[0];
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
            value={current?.task_id || ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {tasks.map((task) => (
              <option key={task.task_id} value={task.task_id}>
                {sourceLabel(task)}
                {tasks.some(
                  (other) =>
                    other !== task && sourceLabel(other) === sourceLabel(task),
                ) && ` · ${task.reg_name} · ${task.started_at}`}
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
      key={`${target}:${current.task_id}:${current.started_at}`}
      task={current}
      target={target}
      toolbar={toolbar}
    />
  ) : (
    <p className="empty-state">{t("onlinePipeline.pending")}</p>
  );
}
