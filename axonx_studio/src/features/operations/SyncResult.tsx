import { useTranslation } from "react-i18next";
import { isRecord } from "../../shared/lib/values";

const fields = ["uploaded", "deferred", "rejected", "oversized"];

export function SyncResult({ value }: { value: unknown }) {
  const { t } = useTranslation();
  if (value == null) {
    return <p className="operation-index-empty">{t("operations.noResult")}</p>;
  }
  const groups =
    isRecord(value) && fields.every((key) => Array.isArray(value[key]))
      ? fields.map((key) => ({ key, items: value[key] as unknown[] }))
      : [];
  return (
    <section className="operation-result operation-sync-result">
      {groups.length > 0 && (
        <dl className="operation-sync-totals">
          {groups.map(({ key, items }) => (
            <div
              key={key}
              className={
                key !== "uploaded" && items.length ? "has-warning" : undefined
              }
            >
              <dt>{t(`operations.metrics.${key}`, key)}</dt>
              <dd>{items.length}</dd>
            </div>
          ))}
        </dl>
      )}
      {groups.length > 0 && groups.every(({ items }) => !items.length) && (
        <p className="operation-index-empty">{t("operations.nothingToSync")}</p>
      )}
      {groups
        .filter(({ items }) => items.length)
        .map(({ key, items }) => (
          <section className="operation-sync-group" key={key}>
            <h3>
              {key === "deferred"
                ? t("operations.unsyncedItems")
                : t(`operations.metrics.${key}`, key)}
            </h3>
            <ul>
              {items.map((item, index) => (
                <li key={index}>
                  {typeof item === "string" ? item : JSON.stringify(item)}
                </li>
              ))}
            </ul>
          </section>
        ))}
      <pre className="operation-sync-json">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}
