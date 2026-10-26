import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { getTaskStatus } from "../tasks/api";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { PipelineReport } from "../online/PipelineReport";
import { TaskReport } from "./TaskReport";

export default function ReportPage({
  taskId,
  target,
  onOpenTask,
}: {
  taskId: string;
  target?: string;
  onOpenTask: (id: string) => void;
}) {
  const { t } = useTranslation();
  const load = useCallback(
    (signal: AbortSignal) => getTaskStatus(taskId, target, signal),
    [taskId, target],
  );
  const { data, error, reload } = useAsyncResource(load);
  return (
    <section className="workspace-page research-canvas">
      {error && (
        <div className="error-state" role="alert">
          {error}
          <button onClick={() => void reload()}>{t("retry")}</button>
        </div>
      )}
      {data ? (
        ["online", "online_pipeline", "compare_pipeline"].includes(
          data.report_kind || "",
        ) ? (
          <PipelineReport
            key={`${target}:${data.task_id}:${data.started_at}`}
            task={data}
            target={target}
            onOpenTask={onOpenTask}
          />
        ) : (
          <TaskReport
            key={`${target}:${data.task_id}:${data.started_at}`}
            task={data}
            target={target}
            onOpenTask={onOpenTask}
          />
        )
      ) : (
        !error && <p>{t("shell.loading")}</p>
      )}
    </section>
  );
}
