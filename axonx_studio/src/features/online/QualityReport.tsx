import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ArtifactFile } from "../research/types";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { loadArtifactRows } from "./api";
import { record, artifactPath } from "./report";
import { ReportTable } from "./ReportTable";
import { parseQuality, type QualitySummary } from "./quality";

export function QualityReport({
  summary,
  taskId,
  artifacts,
  target,
}: {
  summary: QualitySummary;
  taskId: string;
  artifacts?: Record<string, ArtifactFile>;
  target?: string;
}) {
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const [details, setDetails] = useState(false);
  const labelRow = useQualityLabels();
  const checks = summary.checks.filter(
    (check) => showAll || check.matched_count > 0 || check.coverage != null,
  );
  const columns = [
    "stage",
    "reason",
    "action",
    "input_count",
    "output_count",
    "matched_count",
    "removed_count",
    "coverage",
    "threshold",
  ].map((key) => ({
    key,
    label: t(`quality.columns.${key}`),
    format: ["coverage", "threshold"].includes(key)
      ? ("percent" as const)
      : undefined,
  }));
  return (
    <section className="online-quality">
      <header>
        <h3>{t("quality.title")}</h3>
        <span>
          {summary.trade_date} · {summary.trade_time}
        </span>
      </header>
      <p>{t("quality.hint")}</p>
      <label>
        <input
          type="checkbox"
          checked={showAll}
          onChange={(event) => setShowAll(event.target.checked)}
        />
        {t("quality.showAll")}
      </label>
      {!summary.checks.length ? (
        <div className="empty-state">{t("quality.empty")}</div>
      ) : (
        <>
          <ReportTable
            rows={checks.map((check) => labelRow({ ...check }))}
            columns={columns}
          />
          <details>
            <summary>{t("quality.samples")}</summary>
            <ReportTable
              rows={checks.flatMap((check) =>
                check.samples.map((sample) => ({
                  stage: labelRow({ ...check }).stage,
                  reason: labelRow({ ...check }).reason,
                  ts_code: sample.ts_code,
                  details: JSON.stringify(sample),
                })),
              )}
              columns={["stage", "reason", "ts_code", "details"].map((key) => ({
                key,
                label: t(`quality.columns.${key}`),
              }))}
            />
          </details>
        </>
      )}
      {artifacts?.quality_details && (
        <>
          <button
            className="secondary-button"
            aria-expanded={details}
            onClick={() => setDetails(!details)}
          >
            {t("quality.details")}
          </button>
          {details && (
            <QualityDetails
              key={`${target}:${taskId}:${artifacts.quality_details.sha256}`}
              taskId={taskId}
              artifact={artifacts.quality_details}
              target={target}
            />
          )}
        </>
      )}
      {Object.keys(artifacts || {}).some((key) => key.startsWith("debug_")) && (
        <details>
          <summary>{t("quality.debug")}</summary>
          {Object.entries(artifacts || {})
            .filter(([key]) => key.startsWith("debug_"))
            .map(([key, file]) => (
              <code key={key}>{file.path}</code>
            ))}
        </details>
      )}
    </section>
  );
}

function QualityDetails({
  taskId,
  artifact,
  target,
}: {
  taskId: string;
  artifact: ArtifactFile;
  target?: string;
}) {
  const { t } = useTranslation();
  const labelRow = useQualityLabels();
  const load = useCallback(
    (signal: AbortSignal) => loadArtifactRows(taskId, artifact, target, signal),
    [taskId, artifact, target],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  if (error)
    return (
      <div className="error-state" role="alert">
        {error}
        <button onClick={() => void reload()}>
          {t("onlinePipeline.refresh")}
        </button>
      </div>
    );
  if (loading || !data)
    return <div className="loading-state">{t("shell.loading")}</div>;
  const exportDetails = () => {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "quality_details.json";
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <button className="secondary-button" onClick={exportDetails}>
        {t("quality.export")}
      </button>
      <ReportTable
        rows={data.map(labelRow)}
        columns={["stage", "reason", "action", "ts_code", "details"].map(
          (key) => ({ key, label: t(`quality.columns.${key}`) }),
        )}
      />
    </>
  );
}

export function TaskQuality({
  windows,
  taskId,
  target,
}: {
  windows: unknown;
  taskId: string;
  target?: string;
}) {
  const { t } = useTranslation();
  if (!Array.isArray(windows)) return null;
  return windows
    .filter(
      (row) =>
        record(row) && record(row.metrics) && row.metrics.quality != null,
    )
    .map((row) => {
      try {
        const summary = parseQuality(row.metrics.quality);
        if (
          row.artifacts != null &&
          (!record(row.artifacts) ||
            !Object.values(row.artifacts).every(artifactPath))
        )
          throw new Error("Invalid quality artifacts");
        return (
          <details key={row.key} className="online-quality-window">
            <summary>
              {t("quality.title")} · {row.key} ·{" "}
              {t(`onlinePipeline.status.${row.status}`, row.status)}
            </summary>
            <QualityReport
              summary={summary}
              taskId={taskId}
              target={target}
              artifacts={row.artifacts}
            />
          </details>
        );
      } catch (error) {
        return (
          <div key={row.key} className="error-state" role="alert">
            {String(error)}
          </div>
        );
      }
    });
}

function useQualityLabels() {
  const { t } = useTranslation();
  return (row: Record<string, unknown>) => {
    const stage = String(row.stage ?? ""),
      reason = String(row.reason ?? ""),
      action = String(row.action ?? "");
    const parts = stage.split("/");
    const stageLabel =
      parts[0] === "collection"
        ? t("quality.collectionStage", {
            slot: parts[1],
            stage: parts[2]
              ? t(`quality.stages.${parts[2]}`, parts[2])
              : t("quality.stages.collection"),
          })
        : t(`quality.stages.${stage}`, stage);
    return {
      ...row,
      stage: stageLabel,
      reason: reason.startsWith("jump_")
        ? t("quality.jump", { time: reason.slice(5) })
        : t(`quality.reasons.${reason}`, reason),
      action: t(`quality.actions.${action}`, action),
    };
  };
}
