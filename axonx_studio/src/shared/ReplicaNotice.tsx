import { useTranslation } from "react-i18next";
import type { DisplayReplica } from "./api/contracts";

export function ReplicaNotice({
  replica,
  state,
}: {
  replica?: DisplayReplica | null;
  state?: string;
}) {
  const { t, i18n } = useTranslation();
  if (!replica) return null;
  const sampled = Object.entries(replica.files).filter(
    ([, file]) => file.sampled,
  );
  return (
    <aside className="replica-notice">
      <strong>
        {t(replica.snapshot ? "replica.liveLabel" : "replica.label")}
      </strong>
      <p>
        {t(
          replica.snapshot ? "replica.liveDescription" : "replica.description",
        )}
      </p>
      {replica.snapshot && (
        <div className="replica-freshness">
          <time dateTime={replica.snapshot.captured_at}>
            {t("replica.captured", {
              time: new Date(replica.snapshot.captured_at).toLocaleString(
                i18n.resolvedLanguage,
                { hour12: false },
              ),
            })}
          </time>
          <span
            className={
              ["running"].includes(state || "") &&
              Date.now() - Date.parse(replica.snapshot.captured_at) > 120_000
                ? "replica-stale"
                : ""
            }
          >
            {t("replica.age", {
              seconds: Math.max(
                0,
                Math.floor(
                  (Date.now() - Date.parse(replica.snapshot.captured_at)) /
                    1000,
                ),
              ),
            })}
          </span>
          {replica.log && replica.log.start > 0 && (
            <span>{t("replica.logTail")}</span>
          )}
        </div>
      )}
      {(sampled.length > 0 || Object.keys(replica.omitted).length > 0) && (
        <details>
          <summary>{t("replica.coverage")}</summary>
          {sampled.length > 0 && (
            <ul>
              {sampled.map(([name, file]) => (
                <li key={name}>
                  {t("replica.sample", {
                    name,
                    start: file.dates[0] || "—",
                    end: file.dates.at(-1) || "—",
                    rows: file.rows,
                    total: file.source_rows,
                  })}
                </li>
              ))}
            </ul>
          )}
          {Object.keys(replica.omitted).length > 0 && (
            <p>
              {t("replica.omitted", {
                files: Object.keys(replica.omitted).join(", "),
              })}
            </p>
          )}
        </details>
      )}
    </aside>
  );
}
