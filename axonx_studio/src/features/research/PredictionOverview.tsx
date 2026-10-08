import { useTranslation } from "react-i18next";
import type { ResearchArtifact } from "./types";
import { fmt } from "./format";

export function PredictionOverview({ meta }: { meta: ResearchArtifact }) {
  const { t } = useTranslation();
  const stats = meta.prediction_statistics;
  const columns = meta.output_columns?.length
    ? meta.output_columns
    : [
        "trade_date",
        "trade_time",
        "ts_code",
        "pred",
        "name",
        "is_model_candidate",
        "is_buyable_at_signal",
        "signal_price",
        "signal_adjustment_factor",
        "rank",
        "buyable_rank",
        ...(meta.index_weight_columns || []),
      ];
  const rate = (count?: number) =>
    count === undefined || !meta.rows
      ? "—"
      : `${fmt((count / meta.rows) * 100, 1)}%`;
  const indices = Object.entries(stats?.indices || {});
  return (
    <>
      <section className="viz-card wide prediction-overview-card">
        <header>
          <div>
            <small>OVERVIEW</small>
            <h3>{t("research.prediction_overview")}</h3>
          </div>
        </header>
        <div className="prediction-stat-grid">
          <div className="prediction-score-block">
            <small>{t("research.prediction_score_mean")}</small>
            <strong>{fmt(stats?.pred?.mean, 4)}</strong>
            <div className="prediction-score-range">
              <span>
                {t("research.min")} <b>{fmt(stats?.pred?.min, 4)}</b>
              </span>
              <span>
                {t("research.median")} <b>{fmt(stats?.pred?.median, 4)}</b>
              </span>
              <span>
                {t("research.max")} <b>{fmt(stats?.pred?.max, 4)}</b>
              </span>
            </div>
          </div>
          <div className="prediction-coverage-block">
            <small>{t("research.sample_coverage")}</small>
            <div>
              <span>{t("research.symbols_days")}</span>
              <strong>
                {fmt(stats?.symbols, 0)} / {fmt(stats?.days, 0)}
              </strong>
            </div>
            <div>
              <span>{t("research.buyable")}</span>
              <strong>{rate(stats?.buyable_rows)}</strong>
            </div>
            <div>
              <span>{t("research.backtest_candidates")}</span>
              <strong>{rate(stats?.candidate_rows)}</strong>
            </div>
          </div>
        </div>
        <div className="prediction-index-strip">
          <small>{t("research.index_weights")}</small>
          {indices.length ? (
            indices.map(([column, value]) => (
              <span key={column}>
                <code>{column.replace("index_weight_", "").toUpperCase()}</code>
                {fmt(value.constituents, 0)} {t("research.symbols")} ·{" "}
                {fmt(value.days_with_weights, 0)} {t("research.days")}
              </span>
            ))
          ) : (
            <span>
              {(meta.index_weight_columns || [])
                .map((column) =>
                  column.replace("index_weight_", "").toUpperCase(),
                )
                .join(" · ") || "—"}
            </span>
          )}
        </div>
      </section>
      <section className="viz-card wide prediction-columns-card">
        <header>
          <div>
            <small>SCHEMA</small>
            <h3>{t("research.result_columns")}</h3>
          </div>
          <span>{columns.length}</span>
        </header>
        <div className="prediction-column-grid">
          {columns.map((column) => (
            <div key={column}>
              <code>{column}</code>
              <span>
                {column.startsWith("index_weight_")
                  ? t("research.index_weight_decimal")
                  : t(`research.columns.${column}`, { defaultValue: "—" })}
              </span>
            </div>
          ))}
        </div>
        <p>{t("research.pred_is_a_ranking_score")}</p>
      </section>
    </>
  );
}
