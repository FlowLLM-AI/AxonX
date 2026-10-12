import { useTranslation } from "react-i18next";
import type { DisplayReplica } from "./lib/replica";

export function ReplicaNotice({
  replica,
}: {
  replica?: DisplayReplica | null;
}) {
  const { t } = useTranslation();
  if (!replica) return null;
  const sampled = Object.entries(replica.files).filter(
    ([, file]) => file.sampled,
  );
  return (
    <aside className="replica-notice">
      <strong>{t("replica.label")}</strong>
      <p>{t("replica.description")}</p>
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
    </aside>
  );
}
