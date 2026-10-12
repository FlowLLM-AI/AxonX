import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ReportTable, type Column } from "./ReportTable";

export function SignalTable({
  rows,
  previous,
}: {
  rows: Record<string, unknown>[];
  previous: Record<string, unknown>[];
}) {
  const { t } = useTranslation();
  const [buyableOnly, setBuyableOnly] = useState(false);
  const ranks = new Map(previous.map((row) => [row.ts_code, row.rank]));
  const selected = rows
    .filter((row) => !buyableOnly || row.is_buyable_at_signal)
    .map((row) => ({
      ...row,
      rank_change: ranks.has(row.ts_code)
        ? Number(ranks.get(row.ts_code)) - Number(row.rank)
        : null,
    }));
  const fields: [string, Column["format"]?][] = [
    ["rank", "integer"],
    ["ts_code"],
    ["name"],
    ["pred", "score"],
    ["rank_change", "integer"],
    ["buyable_rank", "integer"],
    ["is_buyable_at_signal", "boolean"],
    ["signal_price", "score"],
  ];
  const scores = Object.keys(rows[0] || {}).filter((key) =>
    key.startsWith("pred_seed_"),
  );
  return (
    <>
      <div className="online-report-toolbar">
        <h3>{t("onlineReport.signalTitle")}</h3>
        <label className="online-checkbox">
          <input
            type="checkbox"
            checked={buyableOnly}
            onChange={(e) => setBuyableOnly(e.target.checked)}
          />
          {t("onlineReport.buyableOnly")}
        </label>
      </div>
      <ReportTable
        rows={selected}
        defaultSort="rank"
        columns={[
          ...fields.map(([key, format]) => ({
            key,
            format,
            label: t(`onlineReport.columns.${key}`),
          })),
          ...scores.map((key) => ({
            key,
            label: key,
            format: "score" as const,
          })),
        ]}
      />
      <p className="online-caption">{t("onlineReport.rankHint")}</p>
    </>
  );
}
