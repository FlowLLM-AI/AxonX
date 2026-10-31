import {
  ArrowRight,
  BarChart3,
  BrainCircuit,
  Check,
  CheckCircle2,
  Copy,
  Database,
  GitBranch,
  GitCompareArrows,
  LoaderCircle,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { lazy, Suspense, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import { upstreamTaskIds } from "../../shared/lib/tasks";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { getResearchTask } from "./api";
import { PortfolioView } from "./PortfolioView";
import { BaseOutputView } from "./ResearchOutput";
import type { ResearchKind, ResearchPageId, ResearchTask } from "./types";

const BacktestView = lazy(() =>
  import("./backtest/BacktestView").then((module) => ({
    default: module.BacktestView,
  })),
);

export function ResearchDetail({
  kind,
  taskId,
  target,
  onNavigate,
}: {
  kind: ResearchKind;
  taskId: string;
  target?: string;
  onNavigate: (page: ResearchPageId | "runtime", resource?: string) => void;
}) {
  const { t } = useTranslation();
  const load = useCallback(
    (signal: AbortSignal) => getResearchTask(kind, taskId, { target, signal }),
    [kind, taskId, target],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  if (error)
    return (
      <div className="error-banner" role="alert">
        {error}
        <button onClick={() => void reload()}>{t("research.retry")}</button>
      </div>
    );
  if (loading || !data)
    return (
      <div className="research-loading">
        <LoaderCircle className="spin" />
      </div>
    );
  return <ResearchReport meta={data} target={target} onNavigate={onNavigate} />;
}

function ResearchReport({
  meta,
  target,
  onNavigate,
}: {
  meta: ResearchTask;
  target?: string;
  onNavigate: (page: ResearchPageId | "runtime", resource?: string) => void;
}) {
  const kind = meta.task_type;
  const { t } = useTranslation();
  const lineageClipboard = useCopyFeedback();
  const copiedLineage = lineageClipboard.copied;
  const pageByType: Partial<Record<string, ResearchPageId>> = {
    etl: "etl",
    analysis: "factors",
    train: "train",
    predict: "predict",
    portfolio: "portfolio",
    backtest: "backtest",
  };
  const upstreams = upstreamTaskIds(meta.input_params.upstream_task_ids).map(
    (taskId) => ({
      taskId,
      type: taskId.split("#")[0],
      page: pageByType[taskId.split("#")[0]] || ("runtime" as const),
    }),
  );
  const copyLineageId = (taskId: string) => lineageClipboard.copy(taskId);
  return (
    <>
      {
        <header className="artifact-header">
          <div>
            <span className={`artifact-kind ${kind}`}>{iconFor(kind)}</span>
            <div className="artifact-title">
              <small>{meta.reg_name || kind}</small>
              <div className="artifact-title-row">
                <h2 title={meta.task_id}>{meta.task_id}</h2>
                <button
                  type="button"
                  className="artifact-id-copy"
                  onClick={() => void copyLineageId(meta.task_id)}
                  title={t("research.copy_task_id")}
                  aria-label={t("research.copy_task_id")}
                >
                  {copiedLineage === meta.task_id ? <Check /> : <Copy />}
                </button>
              </div>
            </div>
          </div>
          <div className="artifact-header-actions">
            {kind === "backtest" && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => onNavigate("compare", meta.task_id)}
              >
                <GitCompareArrows />
                {t("research.compare")}
              </button>
            )}
            <span className="ready-badge">
              <CheckCircle2 />
              {t("research.artifacts_ready")}
            </span>
          </div>
        </header>
      }
      <ReplicaNotice replica={meta.replica} />
      {upstreams.length > 0 && (
        <div className="lineage-strip">
          <span>
            <GitBranch />
            {t("research.upstream_tasks")}
          </span>
          <div className="lineage-sources">
            {upstreams.map((upstream) => (
              <div className="lineage-node" key={upstream.taskId}>
                <button
                  className="lineage-link"
                  onClick={() => onNavigate(upstream.page, upstream.taskId)}
                  title={`${t("research.open_upstream_task")}: ${upstream.taskId}`}
                >
                  <em>{upstream.type.toUpperCase()}</em>
                  <code>{upstream.taskId}</code>
                  <ArrowRight />
                </button>
                <button
                  className="lineage-copy"
                  onClick={() => void copyLineageId(upstream.taskId)}
                  aria-label={t("research.copy_upstream_task_id")}
                >
                  {copiedLineage === upstream.taskId ? <Check /> : <Copy />}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      {meta.task_type === "backtest" ? (
        <Suspense
          fallback={
            <div className="research-loading">
              <LoaderCircle className="spin" />
            </div>
          }
        >
          <BacktestView meta={meta} target={target} />
        </Suspense>
      ) : meta.task_type === "portfolio" ? (
        <PortfolioView
          key={`${meta.task_id}:${meta.started_at}`}
          meta={meta}
          target={target}
        />
      ) : (
        <BaseOutputView meta={meta} target={target} />
      )}
    </>
  );
}

const iconFor = (kind: ResearchKind) =>
  kind === "analysis" ? (
    <Sparkles />
  ) : kind === "backtest" ? (
    <TrendingUp />
  ) : kind === "train" ? (
    <BrainCircuit />
  ) : kind === "predict" ? (
    <BarChart3 />
  ) : (
    <Database />
  );
