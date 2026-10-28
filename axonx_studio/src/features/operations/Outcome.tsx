import { useTranslation } from "react-i18next";
import { QualityReport } from "./QualityReport";
import type { OnlineOutcome } from "./report";
import { parseQuality } from "./report";

export function Outcome({
  row,
  taskId,
  target,
}: {
  row: OnlineOutcome;
  taskId: string;
  target?: string;
}) {
  const { t } = useTranslation();
  const coverage = "coverage" in row ? row.coverage : null;
  const rows = "rows" in row ? row.rows : null;
  const elapsed = "elapsed_seconds" in row ? row.elapsed_seconds : null;
  return (
    <section className="online-outcome">
      <header>
        <strong>{row.key}</strong>
        <span className={`online-status status-${row.status}`}>
          {t(`onlinePipeline.status.${row.status}`, row.status)}
        </span>
      </header>
      <div className="online-metrics">
        {coverage != null && (
          <div>
            <span>{t("onlinePipeline.coverage")}</span>
            <strong>{(coverage * 100).toFixed(1)}%</strong>
            <progress max={1} value={coverage} />
          </div>
        )}
        {rows != null && (
          <div>
            <span>{t("onlinePipeline.rows")}</span>
            <strong>{rows.toLocaleString()}</strong>
          </div>
        )}
        {elapsed != null && (
          <div>
            <span>{t("onlinePipeline.elapsed")}</span>
            <strong>{elapsed.toFixed(1)}s</strong>
          </div>
        )}
        {Object.entries(row.metrics || {})
          .filter(([key]) => key !== "quality")
          .map(([key, value]) => (
            <div key={key}>
              <span>{t(`onlinePipeline.metrics.${key}`, key)}</span>
              <strong>
                {typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value)}
              </strong>
            </div>
          ))}
      </div>
      {row.metrics?.quality != null && (
        <QualityReport
          summary={parseQuality(row.metrics.quality)}
          taskId={taskId}
          target={target}
          artifacts={row.artifacts}
        />
      )}
      {row.reason && (
        <p className="online-reason">
          {t(`onlinePipeline.reasons.${row.reason}`, row.reason)}
        </p>
      )}
    </section>
  );
}
