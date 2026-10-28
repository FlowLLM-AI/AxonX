import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { TaskMetadata } from "../../shared/api/contracts";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { isRecord } from "../../shared/lib/values";
import { loadQuality } from "./api";
import { QualityReport, TaskQuality } from "./QualityReport";
import type { OnlineCommit } from "./report";

export type QualitySource = "snapshot" | "before" | "bar" | "model";

/** One source per tab, with samples and full details opened from its check table. */
export function ScopeQuality({
  parent,
  scope,
  live,
  commit,
  target,
  source,
}: {
  parent: TaskMetadata;
  scope: string;
  live: boolean;
  commit?: OnlineCommit;
  target?: string;
  source: QualitySource;
}) {
  const { t } = useTranslation();
  if (source === "model")
    return commit ? (
      <ModelQuality key={commit.commit_id} commit={commit} target={target} />
    ) : (
      <p className="empty-state">{t("onlineWorkbench.noSignal")}</p>
    );
  if (!live)
    return <p className="empty-state">{t("onlineWorkbench.noTaskRecord")}</p>;
  const key = source === "snapshot" ? "snapshot" : `${scope}_${source}`;
  const row = Array.isArray(parent.output_params.windows)
    ? parent.output_params.windows.find(
        (row) =>
          isRecord(row) &&
          row.key === key &&
          isRecord(row.metrics) &&
          row.metrics.quality != null,
      )
    : undefined;
  return row ? (
    <TaskQuality
      key={`${parent.task_id}:${key}`}
      windows={[row]}
      taskId={parent.task_id}
      target={target}
      view="overview"
    />
  ) : (
    <p className="empty-state">{t("quality.empty")}</p>
  );
}

function ModelQuality({
  commit,
  target,
}: {
  commit: OnlineCommit;
  target?: string;
}) {
  const { t } = useTranslation();
  const load = useCallback(
    (signal: AbortSignal) => loadQuality(commit, { target, signal }),
    [commit, target],
  );
  const { data, loading, error, reload } = useAsyncResource(load);
  if (error)
    return (
      <div className="error-state" role="alert">
        {error}
        <button onClick={() => void reload()}>{t("retry")}</button>
      </div>
    );
  if (loading) return <p>{t("shell.loading")}</p>;
  return data ? (
    <QualityReport
      summary={{
        ...data,
        checks: data.checks.filter(
          (check) => !check.stage.startsWith("collection/"),
        ),
      }}
      taskId={commit.task_id}
      artifacts={commit.artifacts}
      target={target}
      view="overview"
    />
  ) : (
    <p className="empty-state">{t("quality.empty")}</p>
  );
}
