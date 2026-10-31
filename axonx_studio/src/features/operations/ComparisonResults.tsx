import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { parseHash, routeHash } from "../../app/routes";
import { taskDirectory } from "../../shared/lib/tasks";
import { isRecord } from "../../shared/lib/values";
import { TopComparison } from "./TopComparison";
import type { CompareModel } from "./compare";
import { parseOnlineReport } from "./report";

export function ComparisonResults({
  model,
  target,
}: {
  model: CompareModel;
  target?: string;
}) {
  const { t } = useTranslation();
  const reports = model.children.filter(
    (node) =>
      node.status?.report_kind === "online" &&
      Array.isArray(node.status.output_params.comparisons),
  );
  try {
    const published = reports.flatMap((node) =>
      (parseOnlineReport(node.status!.output_params).comparisons || []).map(
        (row) => ({
          row,
          taskId: node.status!.task_id,
          startedAt: node.status!.started_at,
        }),
      ),
    );
    const fallback =
      model.finding &&
      typeof model.finding.key === "string" &&
      model.finding.status !== "skipped"
        ? [
            {
              row: parseOnlineReport({ comparisons: [model.finding] })
                .comparisons![0],
              taskId: model.taskId,
              startedAt: model.startedAt,
            },
          ]
        : [];
    const snapshot = model.outcome.comparison;
    const archived = isRecord(snapshot) && isRecord(snapshot.artifacts);
    const results = archived
      ? fallback
      : published.length
        ? published
        : fallback;
    const unavailableReason =
      typeof model.finding?.reason === "string" && model.finding.reason
        ? model.finding.reason
        : model.steps.find(
            (step) =>
              step.name.endsWith(":comparison") && step.state === "skipped",
          )?.error;
    if (!results.length)
      return (
        <p className="compare-empty">
          {unavailableReason
            ? t(
                `onlinePipeline.reasons.${unavailableReason}`,
                unavailableReason,
              )
            : t(
                `nightly.${model.state === "failed" || model.state === "skipped" ? "blocked" : "noResults"}`,
              )}
        </p>
      );
    return (
      <div className="compare-results">
        {results.map(({ row, taskId, startedAt }) => {
          const stages = isRecord(row.metrics?.stages)
            ? row.metrics.stages
            : {};
          const records = Object.entries(stages)
            .filter(([, value]) => isRecord(value))
            .map(([key, value]) => {
              const stage = value as Record<string, unknown>;
              const mismatches = isRecord(stage.mismatches)
                ? stage.mismatches
                : {};
              return {
                key,
                label: t(`nightly.checks.${key}`, key),
                state:
                  stage.consistent === true
                    ? "consistent"
                    : stage.consistent === false
                      ? "different"
                      : "missing",
                offline_rows: stage.offline_rows,
                online_rows: stage.online_rows,
                schema_equal: stage.schema_equal,
                keys_equal: stage.keys_equal,
                mismatches: Object.values(mismatches).filter(
                  (v) => typeof v === "number" && v > 0,
                ).length,
                details: Object.entries(mismatches).map(([field, count]) => ({
                  field,
                  count,
                  error: isRecord(stage.max_absolute_error)
                    ? stage.max_absolute_error[field]
                    : null,
                })),
              };
            })
            .sort(
              (a, b) =>
                Number(a.state === "consistent") -
                Number(b.state === "consistent"),
            );
          return (
            <section key={row.key}>
              {!row.artifacts?.top_comparison && (
                <div className="compare-result-summary">
                  <span className={`online-status status-${row.status}`}>
                    {t(`onlinePipeline.status.${row.status}`, row.status)}
                  </span>
                  {row.reason && (
                    <span>
                      {t(`onlinePipeline.reasons.${row.reason}`, row.reason)}
                    </span>
                  )}
                </div>
              )}
              <TopComparison
                taskId={taskId}
                startedAt={startedAt}
                artifact={row.artifacts?.top_comparison}
                target={target}
                windowKey={row.key}
                status={row.status}
                reason={row.reason}
              />
              <details className="compare-diagnostics" open>
                <summary>
                  <strong>{t("topComparison.diagnostics")}</strong>
                  <span>
                    {t("topComparison.checkSummary", {
                      count: records.length,
                      differences: records.filter(
                        (r) => r.state !== "consistent",
                      ).length,
                    })}
                  </span>
                </summary>
                <div className="comparison-checks">
                  {records.length ? (
                    records.map((record, index) => (
                      <details
                        className={`comparison-check state-${record.state}`}
                        key={record.key}
                        open={index === 0 && record.state === "different"}
                      >
                        <summary>
                          <div className="comparison-check-title">
                            <strong>{record.label}</strong>
                            <span
                              className={`online-status status-${record.state}`}
                            >
                              {t(`onlinePipeline.status.${record.state}`)}
                            </span>
                          </div>
                          <div className="comparison-check-meta">
                            <span>
                              {t("topComparison.rowsPair", {
                                online:
                                  typeof record.online_rows === "number"
                                    ? record.online_rows.toLocaleString()
                                    : "—",
                                offline:
                                  typeof record.offline_rows === "number"
                                    ? record.offline_rows.toLocaleString()
                                    : "—",
                              })}
                            </span>
                            <span>
                              {t("topComparison.fieldCount", {
                                count: record.mismatches,
                              })}
                            </span>
                            <span
                              className={
                                record.schema_equal === false
                                  ? "comparison-check-issue"
                                  : ""
                              }
                            >
                              {t("nightly.schema")} ·{" "}
                              {record.schema_equal === true
                                ? t("onlineReport.yes")
                                : record.schema_equal === false
                                  ? t("onlineReport.no")
                                  : "—"}
                            </span>
                            <span
                              className={
                                record.keys_equal === false
                                  ? "comparison-check-issue"
                                  : ""
                              }
                            >
                              {t("nightly.keys")} ·{" "}
                              {record.keys_equal === true
                                ? t("onlineReport.yes")
                                : record.keys_equal === false
                                  ? t("onlineReport.no")
                                  : "—"}
                            </span>
                          </div>
                        </summary>
                        <div className="comparison-check-fields">
                          {record.details.some((d) => Number(d.count) > 0) ? (
                            <table className="compare-field-details">
                              <thead>
                                <tr>
                                  <th>{t("topComparison.field")}</th>
                                  <th>{t("topComparison.differences")}</th>
                                  <th>{t("nightly.maxError")}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {record.details
                                  .filter((d) => Number(d.count) > 0)
                                  .sort(
                                    (a, b) => Number(b.count) - Number(a.count),
                                  )
                                  .map((d) => (
                                    <tr key={d.field}>
                                      <td>
                                        <code>{d.field}</code>
                                      </td>
                                      <td>
                                        {Number(d.count).toLocaleString()}
                                      </td>
                                      <td>
                                        {typeof d.error === "number"
                                          ? d.error.toExponential(3)
                                          : "—"}
                                      </td>
                                    </tr>
                                  ))}
                              </tbody>
                            </table>
                          ) : (
                            <p>{t("topComparison.noFieldDifferences")}</p>
                          )}
                        </div>
                      </details>
                    ))
                  ) : (
                    <p className="compare-empty">
                      {t("nightly.noCheckDetails")}
                    </p>
                  )}
                </div>
              </details>
              {taskId && Object.keys(row.artifacts || {}).length > 0 && (
                <div className="compare-artifacts">
                  {Object.entries(row.artifacts || {}).map(([role, file]) => (
                    <a
                      key={role}
                      href={routeHash(
                        parseHash(window.location.hash).machineId,
                        {
                          section: "workspace",
                          view: "files",
                          resource: `${taskDirectory(taskId)}/${file.path}`,
                        },
                      )}
                    >
                      <FileText aria-hidden="true" />
                      {file.path.split("/").at(-1)}
                    </a>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    );
  } catch (reason) {
    return (
      <p className="online-warning" role="alert">
        {String(reason)}
      </p>
    );
  }
}
