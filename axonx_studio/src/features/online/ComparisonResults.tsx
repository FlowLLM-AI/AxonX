import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { parseHash, routeHash } from "../../app/routes";
import { taskDirectory } from "../../shared/lib/tasks";
import { isRecord } from "../../shared/lib/values";
import { parseOnlineReport } from "./types";
import { ReportTable } from "./ReportTable";
import type { CompareModel } from "./compare";

export function ComparisonResults({
  model,
  portfolio = false,
}: {
  model: CompareModel;
  portfolio?: boolean;
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
        (row) => ({ row, taskId: node.status!.task_id }),
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
              taskId: "",
            },
          ]
        : [];
    const results = published.length ? published : fallback;
    if (!results.length)
      return (
        <p className="compare-empty">
          {t(
            `nightly.${model.state === "failed" || model.state === "skipped" || model.state === "cancelled" ? "blocked" : "noResults"}`,
          )}
        </p>
      );
    return (
      <div className="compare-results">
        {results.map(({ row, taskId }) => {
          const stages = isRecord(row.metrics?.stages)
            ? row.metrics.stages
            : {};
          const ledger = new Set([
            "signals",
            "orders",
            "positions",
            "trades",
            "daily",
          ]);
          const records = Object.entries(stages)
            .filter(
              ([key, value]) =>
                isRecord(value) && ledger.has(key) === portfolio,
            )
            .map(([key, value]) => {
              const stage = value as Record<string, unknown>;
              const mismatches = isRecord(stage.mismatches)
                ? stage.mismatches
                : {};
              const errors = isRecord(stage.max_absolute_error)
                ? Object.values(stage.max_absolute_error).filter(
                    (v): v is number =>
                      typeof v === "number" && Number.isFinite(v),
                  )
                : [];
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
                mismatches:
                  Object.entries(mismatches)
                    .filter(([, v]) => typeof v === "number" && v > 0)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(" · ") || "—",
                max_error: errors.length ? Math.max(...errors) : null,
              };
            })
            .sort(
              (a, b) =>
                Number(a.state === "consistent") -
                Number(b.state === "consistent"),
            );
          return (
            <section key={row.key}>
              {!portfolio && (
                <div className="compare-result-summary">
                  <span className={`online-status status-${row.status}`}>
                    {t(`onlinePipeline.status.${row.status}`, row.status)}
                  </span>
                  {row.reason && (
                    <span>
                      {t(`onlinePipeline.reasons.${row.reason}`, row.reason)}
                    </span>
                  )}
                  {Object.entries(row.metrics || {})
                    .filter(([k, v]) => k !== "stages" && typeof v !== "object")
                    .map(([k, v]) => (
                      <span key={k}>
                        {t(`onlinePipeline.metrics.${k}`, k)}{" "}
                        <strong>{String(v)}</strong>
                      </span>
                    ))}
                </div>
              )}
              {records.length > 0 ? (
                <ReportTable
                  rows={records}
                  columns={[
                    { key: "label", label: t("nightly.check") },
                    {
                      key: "state",
                      label: t("nightly.result"),
                      render: (r) => (
                        <span className={`online-status status-${r.state}`}>
                          {t(`onlinePipeline.status.${r.state}`)}
                        </span>
                      ),
                    },
                    {
                      key: "offline_rows",
                      label: t("nightly.offlineRows"),
                      format: "integer",
                    },
                    {
                      key: "online_rows",
                      label: t("nightly.onlineRows"),
                      format: "integer",
                    },
                    {
                      key: "schema_equal",
                      label: t("nightly.schema"),
                      render: (r) =>
                        typeof r.schema_equal !== "boolean"
                          ? "—"
                          : t(
                              r.schema_equal === true
                                ? "onlineReport.yes"
                                : "onlineReport.no",
                            ),
                    },
                    {
                      key: "keys_equal",
                      label: t("nightly.keys"),
                      render: (r) =>
                        typeof r.keys_equal !== "boolean"
                          ? "—"
                          : t(
                              r.keys_equal === true
                                ? "onlineReport.yes"
                                : "onlineReport.no",
                            ),
                    },
                    { key: "mismatches", label: t("nightly.differences") },
                    {
                      key: "max_error",
                      label: t("nightly.maxError"),
                      render: (r) =>
                        typeof r.max_error === "number"
                          ? r.max_error.toExponential(3)
                          : "—",
                    },
                  ]}
                />
              ) : (
                <p className="compare-empty">
                  {t(portfolio ? "nightly.noLedger" : "nightly.noCheckDetails")}
                </p>
              )}
              {!portfolio &&
                taskId &&
                Object.keys(row.artifacts || {}).length > 0 && (
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
