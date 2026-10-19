import { useTranslation } from "react-i18next";
import { isRecord } from "../../shared/lib/values";
import { ReportTable } from "../online/ReportTable";
import { display } from "../online/format";

const syncFields = ["uploaded", "deferred", "rejected", "oversized"];
const warningFields = new Set([
  "deferred",
  "rejected",
  "oversized",
  "rejected_count",
]);

/** Present persisted outcomes without interpreting a successful Job as complete delivery. */
export function OperationResult({ value }: { value: unknown }) {
  const { t } = useTranslation();
  if (value == null || (isRecord(value) && !Object.keys(value).length))
    return <p className="operation-index-empty">{t("operations.noResult")}</p>;
  const entries = isRecord(value) ? Object.entries(value) : [];
  const isSync = syncFields.every((key) =>
    Array.isArray(isRecord(value) ? value[key] : null),
  );
  const metrics = entries.filter(
    ([, item]) => typeof item === "number" || Array.isArray(item),
  );
  const facts = entries.filter(
    ([key, item]) =>
      item != null &&
      !["run_id", "task_id", "status", "artifacts"].includes(key) &&
      ["string", "boolean"].includes(typeof item),
  );
  const warnings = metrics.filter(
    ([key, item]) =>
      warningFields.has(key) &&
      (Array.isArray(item) ? item.length : Number(item)) > 0,
  );
  const outcome = isRecord(value) ? value.status : undefined;
  return (
    <section className="operation-result">
      {(outcome === "partial" ||
        outcome === "failed" ||
        warnings.length > 0) && (
        <p className="operation-outcome-warning" role="status">
          {t("operations.incompleteResult")}
        </p>
      )}
      {isSync &&
        syncFields.every(
          (key) => (value as Record<string, unknown[]>)[key].length === 0,
        ) && <p>{t("operations.nothingToSync")}</p>}
      {metrics.length > 0 && (
        <dl className="operation-metrics">
          {metrics.map(([key, item]) => (
            <div
              key={key}
              className={
                warningFields.has(key) &&
                (Array.isArray(item) ? item.length : Number(item)) > 0
                  ? "operation-outcome-warning"
                  : undefined
              }
            >
              <dt>{t(`operations.metrics.${key}`, key)}</dt>
              <dd>{display(Array.isArray(item) ? item.length : item)}</dd>
            </div>
          ))}
        </dl>
      )}
      {facts.length > 0 && (
        <dl className="operation-facts">
          {facts.map(([key, item]) => (
            <div key={key}>
              <dt>{t(`operations.fields.${key}`, key)}</dt>
              <dd>{display(item)}</dd>
            </div>
          ))}
        </dl>
      )}
      {entries
        .filter(([, item]) => Array.isArray(item) && item.length > 0)
        .map(([key, item]) => (
          <details key={key} className="operation-result-details">
            <summary>
              {t(`operations.metrics.${key}`, key)} ·{" "}
              {(item as unknown[]).length}
            </summary>
            <ReportTable
              rows={(item as unknown[]).map((entry) => ({
                item: typeof entry === "string" ? entry : JSON.stringify(entry),
              }))}
              columns={[{ key: "item", label: t("operations.items") }]}
            />
          </details>
        ))}
      <details className="operation-result-details">
        <summary>{t("operations.rawResult")}</summary>
        <pre>{JSON.stringify(value, null, 2)}</pre>
      </details>
    </section>
  );
}
