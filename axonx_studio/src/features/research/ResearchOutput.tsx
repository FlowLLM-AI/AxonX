import { FileSpreadsheet, LoaderCircle } from "lucide-react";
import { lazy, Suspense, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { formatNumber as fmt, formatBytes } from "../../shared/lib/format";
import { taskDirectory } from "../../shared/lib/tasks";
import { countTrainingMembers } from "./api";
import { AnalysisScores } from "./FactorScores";
import { PredictionOverview } from "./PredictionOverview";
import type { ResearchTask } from "./types";

const TrainingCurveChart = lazy(() =>
  import("./TrainingCurveChart").then((module) => ({
    default: module.TrainingCurveChart,
  })),
);

function Kpis({
  items,
}: {
  items: { label: string; value: React.ReactNode; hint?: string }[];
}) {
  return (
    <div className={`artifact-kpis count-${Math.min(items.length, 4)}`}>
      {items.map((item) => (
        <article key={item.label}>
          <small>{item.label}</small>
          <strong>{item.value}</strong>
          {item.hint && <span>{item.hint}</span>}
        </article>
      ))}
    </div>
  );
}

function TrainingMemberCount({
  meta,
  target,
}: {
  meta: ResearchTask<"train">;
  target?: string;
}) {
  const load = useCallback(
    (signal: AbortSignal) => countTrainingMembers(meta, { target, signal }),
    [meta, target],
  );
  const { data, error } = useAsyncResource(load);
  return (
    <span title={error || undefined}>{data == null ? "—" : fmt(data, 0)}</span>
  );
}

export function BaseOutputView({
  meta,
  target,
}: {
  meta: Exclude<ResearchTask, { task_type: "backtest" }>;
  target?: string;
}) {
  const kind = meta.task_type;
  const { t } = useTranslation();
  const train = meta.task_type === "train" ? meta.output_params : null;
  const etl = meta.task_type === "etl" ? meta.output_params : null;
  const predict = meta.task_type === "predict" ? meta.output_params : null;
  const analysis = meta.task_type === "analysis" ? meta.output_params : null;
  const count =
    train?.train_rows ??
    ("rows" in meta.output_params ? meta.output_params.rows : undefined);
  const countLabel =
    kind === "train"
      ? t("research.train_rows")
      : kind === "predict"
        ? t("research.prediction_rows")
        : t("research.rows");

  const members = Object.entries(
    (("protocol" in meta.output_params
      ? meta.output_params.protocol.score_columns
      : undefined) || {}) as Record<string, string>,
  );
  const columns =
    kind === "etl"
      ? [
          [
            t("research.feature_columns"),
            etl?.feature_columns ?? train?.feature_columns,
          ],
          [t("research.label_columns"), etl?.label_columns],
        ]
      : kind === "train"
        ? [
            [
              t("research.feature_columns"),
              etl?.feature_columns ?? train?.feature_columns,
            ],
            [t("research.target_columns"), train?.target_columns],
          ]
        : [];
  const columnCards = columns.map(([title, values]) =>
    Array.isArray(values) && (values.length > 0 || kind === "train") ? (
      <section className="viz-card base-columns-card" key={String(title)}>
        <header>
          <div>
            <small>COLUMNS</small>
            <h3>{title}</h3>
          </div>
          <span>{values.length}</span>
        </header>
        <div className="base-column-list">
          {values.map((value) => (
            <code key={value}>{value}</code>
          ))}
        </div>
      </section>
    ) : null,
  );
  return (
    <div className="artifact-content">
      <Kpis
        items={[
          { label: countLabel, value: fmt(count, 0) },
          ...(kind === "train"
            ? [
                {
                  label: t("research.model"),
                  value: train?.model_name || "—",
                },
              ]
            : []),
          ...(kind === "train" || kind === "predict"
            ? [
                {
                  label: t("research.model_members"),
                  value:
                    meta.task_type === "train" ? (
                      <TrainingMemberCount meta={meta} target={target} />
                    ) : (
                      fmt(members.length, 0)
                    ),
                },
              ]
            : []),
          ...(kind === "etl" || kind === "predict"
            ? [
                {
                  label: t("research.start"),
                  value: (etl?.date_range ?? predict?.date_range)?.start || "—",
                },
                {
                  label: t("research.end"),
                  value: (etl?.date_range ?? predict?.date_range)?.end || "—",
                },
              ]
            : []),
          {
            label: t("research.artifacts"),
            value: fmt(
              Object.keys(meta.output_params.artifacts || {}).length,
              0,
            ),
          },
        ]}
      />
      {kind === "train" ? (
        <div className="train-config-grid">
          {columnCards}
          <section className="viz-card train-parameters-card">
            <header>
              <div>
                <small>PARAMETERS</small>
                <h3>{t("research.effective_parameters")}</h3>
              </div>
              <span>{Object.keys(train?.parameters || {}).length}</span>
            </header>
            <div className="base-value-list">
              {Object.entries(train?.parameters || {}).map(([name, value]) => (
                <div key={name}>
                  <code>{name}</code>
                  <strong>
                    {typeof value === "string" ? value : JSON.stringify(value)}
                  </strong>
                </div>
              ))}
            </div>
          </section>
        </div>
      ) : meta.task_type === "predict" ? (
        <PredictionOverview meta={meta} />
      ) : (
        columnCards
      )}
      {kind === "predict" && members.length > 0 && (
        <section className="viz-card wide">
          <header>
            <h3>{t("research.score_columns")}</h3>
            <span>{members.length}</span>
          </header>
          <div className="base-value-list">
            {members.map(([member, column]) => (
              <div key={member}>
                <code>{member}</code>
                <strong>{column}</strong>
              </div>
            ))}
          </div>
        </section>
      )}
      {kind === "analysis" && (
        <AnalysisScores scores={analysis?.scores || {}} />
      )}
      {kind === "train" && (
        <section className="viz-card wide train-curve-card">
          <header>
            <div>
              <small>TRAINING</small>
              <h3>{t("research.training_curves")}</h3>
            </div>
          </header>
          {train?.training_curve?.x.length ? (
            <Suspense
              fallback={
                <div className="research-loading">
                  <LoaderCircle className="spin" />
                </div>
              }
            >
              <TrainingCurveChart curve={train?.training_curve} />
            </Suspense>
          ) : (
            <div className="train-curve-empty">
              {t("research.no_training_curve_is_available")}
            </div>
          )}
          {Object.keys(train?.metrics || {}).length > 0 && (
            <div className="train-curve-metrics">
              {Object.entries(train?.metrics || {}).map(([name, value]) => (
                <span key={name}>
                  <small>{name}</small>
                  <strong>{fmt(value, 4)}</strong>
                </span>
              ))}
            </div>
          )}
        </section>
      )}
      <section className="viz-card base-files-card">
        <header>
          <div>
            <small>OUTPUT</small>
            <h3>{t("research.output_files")}</h3>
          </div>
        </header>
        <div className="artifact-files">
          {Object.entries(meta.output_params.artifacts).map(([name, file]) => (
            <div key={name}>
              <FileSpreadsheet />
              <span>
                <strong>{name}</strong>
                <code>
                  {taskDirectory(meta.task_id)}/{file.path}
                </code>
              </span>
              <em>{formatBytes(file.size, false)}</em>
            </div>
          ))}
        </div>
        {kind === "etl" && typeof meta.input_params.input_dir === "string" && (
          <div className="artifact-input-dir">
            <small>{t("research.input_directory")}</small>
            <code>{String(meta.input_params.input_dir)}</code>
          </div>
        )}
      </section>
    </div>
  );
}
