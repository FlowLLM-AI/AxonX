import type { ReactNode } from "react";
import { isArtifactRecord } from "../../shared/api/artifacts";
import { isRecord } from "../../shared/lib/values";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ArtifactRecord } from "../../shared/api/contracts";

import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { loadArtifactRows } from "./api";
import { parseQuality, type QualitySummary } from "./quality";

import { ReportTable } from "./ReportTable";
import { display } from "./format";

export type QualityView = "checks" | "samples" | "details" | "overview";

export function QualityReport({
  summary,
  taskId,
  artifacts,
  target,
  files,
  view: controlledView,
}: {
  summary: QualitySummary;
  taskId: string;
  artifacts?: Record<string, ArtifactRecord>;
  target?: string;
  files?: ReactNode;
  view?: QualityView;
}) {
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const [expandedChecks, setExpandedChecks] = useState(new Set<string>());
  const labelRow = useQualityLabels();
  const [selectedView, setView] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const view = controlledView || selectedView;
  const warnings = summary.checks.filter(
    (check) => check.matched_count > 0,
  ).length;
  const passed = summary.checks.filter(
    (check) => check.input_count > 0 && check.matched_count === 0,
  ).length;
  const noData = summary.checks.filter(
    (check) => check.input_count === 0,
  ).length;
  const checks = summary.checks.filter((check) =>
    view === "overview"
      ? check.input_count > 0
      : showAll || check.matched_count > 0 || check.coverage != null,
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
  const views = [
    { id: "checks", label: t("quality.checksTab") },
    { id: "samples", label: t("quality.samplesTab") },
    ...(artifacts?.quality_details
      ? [{ id: "details", label: t("quality.details") }]
      : []),
    ...(Object.keys(artifacts || {}).some((key) => key.startsWith("debug_"))
      ? [{ id: "debug", label: t("quality.debug") }]
      : []),
  ];
  const content = (
    <>
      {view === "overview" && (
        <p className="quality-result-summary">
          {t("quality.resultCounts", { warnings, passed })}
          {noData > 0 && ` · ${t("quality.noDataCount", { count: noData })}`}
        </p>
      )}
      {(view === "checks" || view === "overview") && (
        <ReportTable
          rows={[...checks]
            .sort(
              (a, b) =>
                Number(b.matched_count > 0) - Number(a.matched_count > 0),
            )
            .map((check) => {
              const labels = labelRow({ ...check });
              return {
                ...labels,
                check: `${labels.stage} · ${t(`quality.checkNames.${check.reason}`, String(labels.reason))}`,
                resultState: check.matched_count > 0 ? "incomplete" : "done",
                result: t(
                  `quality.actions.${check.input_count === 0 ? "no_data" : check.matched_count > 0 ? "warning" : "passed"}`,
                ),
                description: [
                  t("quality.checkedCount", { count: check.input_count }),
                  check.matched_count > 0
                    ? t("quality.issueCount", { count: check.matched_count })
                    : t("quality.noIssues"),
                  ...(check.matched_count > 0 && check.action !== "warning"
                    ? [String(labels.action)]
                    : []),
                  ...(check.removed_count > 0
                    ? [
                        t("quality.remainingCount", {
                          count: check.output_count,
                        }),
                      ]
                    : []),
                  ...(check.coverage != null
                    ? [
                        t("quality.coverageValue", {
                          value: display(check.coverage, "percent"),
                        }),
                      ]
                    : []),
                  ...(check.threshold != null
                    ? [
                        t("quality.thresholdValue", {
                          value: display(check.threshold, "percent"),
                        }),
                      ]
                    : []),
                ].join(" · "),
                samples: check.samples,
                checkKey: JSON.stringify([
                  check.stage,
                  check.reason,
                  check.action,
                ]),
              };
            })}
          columns={
            view === "overview"
              ? [
                  ...["check", "result", "description"].map((key) => ({
                    key,
                    label: t(`quality.columns.${key}`),
                    ...(key === "result"
                      ? {
                          render: (row: Record<string, unknown>) => (
                            <span
                              className={`online-status status-${row.resultState}`}
                            >
                              {String(row.result)}
                            </span>
                          ),
                        }
                      : {}),
                  })),
                  {
                    key: "samples",
                    label: t("quality.samplesTab"),
                    render: (row: Record<string, unknown>) => {
                      const samples = row.samples as Record<string, unknown>[];
                      return samples.length ? (
                        <button
                          type="button"
                          className="secondary-button"
                          aria-expanded={expandedChecks.has(
                            String(row.checkKey),
                          )}
                          onClick={() =>
                            setExpandedChecks((current) => {
                              const next = new Set(current);
                              const key = String(row.checkKey);
                              if (next.has(key)) next.delete(key);
                              else next.add(key);
                              return next;
                            })
                          }
                        >
                          {t("quality.viewSamples", { count: samples.length })}
                        </button>
                      ) : (
                        "—"
                      );
                    },
                  },
                ]
              : columns
          }
          renderExpanded={
            view === "overview"
              ? (row) =>
                  expandedChecks.has(String(row.checkKey)) ? (
                    <ul className="quality-inline-samples">
                      {(row.samples as Record<string, unknown>[]).map(
                        (sample, index) => (
                          <li key={index}>
                            <strong>{String(sample.ts_code || "—")}</strong>
                            <code>{JSON.stringify(sample)}</code>
                          </li>
                        ),
                      )}
                    </ul>
                  ) : null
              : undefined
          }
          actions={
            view === "overview" ? undefined : (
              <button
                type="button"
                className="secondary-button"
                aria-pressed={showAll}
                disabled={!summary.checks.length}
                onClick={() => setShowAll((value) => !value)}
              >
                {t(showAll ? "quality.showRelevant" : "quality.showAll")}
              </button>
            )
          }
        />
      )}
      {view === "samples" && (
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
      )}
      {view === "details" && artifacts?.quality_details && (
        <QualityDetails
          key={`${target}:${taskId}:${artifacts.quality_details.revision}`}
          taskId={taskId}
          artifact={artifacts.quality_details}
          target={target}
        />
      )}
      {view === "debug" &&
        Object.entries(artifacts || {})
          .filter(([key]) => key.startsWith("debug_"))
          .map(([key, file]) => (
            <code key={key}>{file.path.split(/[\\/]/).pop()}</code>
          ))}
      {view === "details" && !artifacts?.quality_details && (
        <p className="empty-state">{t("quality.empty")}</p>
      )}
    </>
  );
  return (
    <section className="online-quality">
      {files}
      {controlledView ? (
        content
      ) : (
        <div className="quality-summary-bar">
          <span>
            {t("quality.title")} ·{" "}
            {t("quality.checkCount", { count: summary.checks.length })}
          </span>
          {views.map((item) => (
            <button
              key={item.id}
              className="secondary-button"
              type="button"
              aria-expanded={view === item.id}
              onClick={() =>
                setView((value) => (value === item.id ? null : item.id))
              }
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
      {view === "overview" && artifacts?.quality_details && (
        <details
          className="quality-inline-details"
          onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
        >
          <summary>{t("quality.details")}</summary>
          {detailsOpen && (
            <QualityDetails
              key={`${target}:${taskId}:${artifacts.quality_details.revision}`}
              taskId={taskId}
              artifact={artifacts.quality_details}
              target={target}
            />
          )}
        </details>
      )}
      {!controlledView && view && (
        <section className="quality-inline-details">{content}</section>
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
  artifact: ArtifactRecord;
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
    <ReportTable
      actions={
        <button
          type="button"
          className="online-table-icon-button"
          aria-label={t("quality.export")}
          title={t("quality.export")}
          onClick={exportDetails}
        >
          <span aria-hidden="true">📥</span>
        </button>
      }
      rows={data.map(labelRow)}
      columns={["stage", "reason", "action", "ts_code", "details"].map(
        (key) => ({ key, label: t(`quality.columns.${key}`) }),
      )}
    />
  );
}

export function TaskQuality({
  windows,
  windowKey,
  excludeKeys = [],
  files,
  taskId,
  target,
  view,
}: {
  windows: unknown;
  windowKey?: string;
  excludeKeys?: string[];
  files?: ReactNode;
  taskId: string;
  target?: string;
  view?: QualityView;
}) {
  const { t } = useTranslation();
  if (!Array.isArray(windows)) return files;
  const rows = windows.filter(
    (row) =>
      isRecord(row) &&
      (windowKey === undefined || row.key === windowKey) &&
      !excludeKeys.includes(String(row.key)) &&
      isRecord(row.metrics) &&
      row.metrics.quality != null,
  );
  if (!rows.length) return files;
  return rows.map((row) => {
    try {
      const summary = parseQuality(row.metrics.quality);
      if (
        row.artifacts != null &&
        (!isRecord(row.artifacts) ||
          !Object.values(row.artifacts).every(isArtifactRecord))
      )
        throw new Error("Invalid quality artifacts");
      return (
        <section key={row.key} className="online-quality-window">
          {files === undefined && !view && (
            <header>
              {t("quality.title")} · {row.key} ·{" "}
              {t(`onlinePipeline.status.${row.status}`, row.status)}
              <small>
                {summary.trade_date} · {summary.trade_time}
              </small>
            </header>
          )}
          <QualityReport
            files={files}
            view={view}
            summary={summary}
            taskId={taskId}
            target={target}
            artifacts={row.artifacts}
          />
        </section>
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
      action =
        row.input_count === 0
          ? "no_data"
          : row.matched_count === 0
            ? "passed"
            : String(row.action ?? "");
    const parts = stage.split("/");
    const slot = /^(\d{2})(\d{2})_(before|bar)$/.exec(stage);
    const slotLabel = slot
      ? t(`quality.slotStages.${slot[3]}`, { time: `${slot[1]}:${slot[2]}` })
      : stage;
    const stageLabel =
      parts[0] === "collection"
        ? t("quality.collectionStage", {
            slot: parts[1],
            stage:
              parts[2] && parts[2] !== parts[1]
                ? t(`quality.stages.${parts[2]}`, parts[2])
                : t("quality.stages.collection"),
          })
        : t(`quality.stages.${stage}`, slotLabel);
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
